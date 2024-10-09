"""In built actors with focus on Spoken Dialog Systems."""

from evdm.bus import BusType
from evdm.events import make_event
from evdm.actors.core import Actor
import sounddevice as sd
import asyncio
from collections import deque
import numpy as np


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
