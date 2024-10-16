"""In built actors with focus on Spoken Dialog Systems."""

from evdm.bus import BusType, make_event
from evdm.actors.core import Actor
import sounddevice as sd
import asyncio
from collections import deque
import numpy as np
from deepgram import (DeepgramClient, LiveOptions, LiveTranscriptionEvents, Microphone)
import os
from loguru import logger


class MicrophoneListener(Actor):
    """Actor that reads audio chunks from microphone directly (not via Device
    bus) and puts events on the AudioSignals bus.
    """

    def __init__(self, chunk_size: int = 50, samplerate: int = 48_000) -> None:
        """`chunk_size` tells the size of each emitted chunk in ms. You could
        get a lower sized chunk when the source has stopped emitting audio.
        """
        self.sr = samplerate
        self.chunk_size = chunk_size

    async def act(self, event, heb):
        q = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _callback(indata, frame_count, time_info, status):
            loop.call_soon_threadsafe(q.put_nowait, (indata.copy(), status))

        stream = sd.InputStream(
            callback=_callback,
            channels=1,
            blocksize=int((self.chunk_size / 1000) * self.sr),
            samplerate=self.sr
        )

        with stream:
            while True:
                indata, status = await q.get()
                await heb.put(make_event({
                    "source": "microphone",
                    "samples": indata,
                    "sr": self.sr
                }), BusType.AudioSignals)


class DeepgramTranscriber(Actor):
    """Listen to audio from microphone directly and emit tokens on Texts bus,
    optionally tagged with speaker id if diarization is enabled.

    End of utterance events are emitted on Semantics bus. All final tokens till
    last EoU or start should be counted as utterance.
    """

    def __init__(self, language: str, diarize = False) -> None:
        super().__init__()

        api_key = os.getenv("DG_API_KEY")
        if api_key is None:
            raise RuntimeError("DG_API_KEY is not set")

        self.client = DeepgramClient(api_key)
        self.conn = None
        self.heb = None
        self.language = language
        self.diarize = diarize

    async def act(self, event, heb):
        """Take any event as the trigger to start listening. Once a connection
        is established, ignore any further event's reading as trigger.
        """

        if self.conn:
            return

        if self.heb is None:
            self.heb = heb

        async def on_error(_self, error, **kwargs):
            logger.error(kwargs["error"])

        async def on_message(_self, result, **kwargs):
            alt = result.channel.alternatives[0]
            if len(alt.transcript) == 0:
                return

            for word in alt.words:
                await self.heb.put(make_event({
                    "source": f"deepgram:spk{word.speaker}" if self.diarize else "deepgram",
                    "text": word.punctuated_word,
                    "is_final": result.is_final,
                    "start": word.start,
                    "end": word.end,
                    "confidence": word.confidence
                }), BusType.Texts)

        async def on_metadata(_self, metadata, **kwargs):
            logger.debug(metadata)

        async def on_speech_started(_self, speech_started, **kwargs):
            logger.debug(speech_started)

        async def on_utterance_end(_self, utterance_end, **kwargs):
            await self.heb.put(make_event({
                "source": "deepgram",
                "signal": "eou",
            }), BusType.Semantics)

        self.conn = self.client.listen.asyncwebsocket.v("1")

        self.conn.on(LiveTranscriptionEvents.Transcript, on_message)
        self.conn.on(LiveTranscriptionEvents.Metadata, on_metadata)
        self.conn.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
        self.conn.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
        self.conn.on(LiveTranscriptionEvents.Error, on_error)

        options = LiveOptions(
            model="nova-2",
            smart_format=True,
            language=self.language,
            encoding="linear16",
            channels=1,
            sample_rate=24_000,
            interim_results=True,
            utterance_end_ms="1000",
            vad_events=True,
            diarize=self.diarize
        )

        if await self.conn.start(options) is False:
            raise RuntimeError(f"Failed to connect to Deepgram")

        self.mic = Microphone(self.conn.send)
        self.mic.start()

    async def close(self):
        self.mic.finish()
        await self.conn.finish()


class SpeakerPlayer(Actor):
    """Play audio from AudioSignals bus directly (without involving device bus)
    without buffering.
    """

    def __init__(self, source: str) -> None:
        """Only play audio from the given `source` name on Audio Signals bus.
        """

        self.sr = None
        self.source = source
        self.audio_buffer = deque()
        self.buffer_ready = asyncio.Event()

    async def play_audio(self):
        def audio_callback(outdata, frames, time, status):
            if len(self.audio_buffer) < frames:
                outdata[:] = np.zeros((frames, 1), dtype="float32")
            else:
                for i in range(frames):
                    outdata[i] = self.audio_buffer.popleft()

        stream = sd.OutputStream(
            samplerate=self.sr,
            channels=1,
            dtype="float32",
            callback=audio_callback
        )

        with stream:
            while True:
                await self.buffer_ready.wait()
                self.buffer_ready.clear()

    def feed_audio(self, samples):
        self.audio_buffer.extend(samples)

        if len(self.audio_buffer) > self.sr * 0.3:
            self.buffer_ready.set()

    async def act(self, event, heb):
        """
        Event's `data` structure is like the following:

        - `source`: Label for the source of this event.
        - `samples`: np.ndarray containing the audio samples.
        - `sr`: Sampling rate of the audio data.
        """

        if event.data["source"] != self.source:
            return

        if self.sr == None:
            self.sr = event.data["sr"]

            asyncio.create_task(self.play_audio())

        samples = event.data["samples"]
        self.feed_audio(samples)
