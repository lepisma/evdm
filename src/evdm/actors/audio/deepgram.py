from evdm.core import Actor, Emitter, BusType, make_event
from deepgram import (DeepgramClient, LiveOptions, LiveTranscriptionEvents, Microphone)
import os
from loguru import logger


class DeepgramTranscriber(Actor, Emitter):
    """Listen to audio from microphone directly and emit tokens on Texts bus,
    optionally tagged with speaker id if diarization is enabled.

    End of utterance events are emitted on Semantics bus. All final tokens till
    last EoU or start should be counted as utterance.
    """

    def __init__(self, language: str, diarize = False, label = "asr") -> None:
        """
        `label` is used in the 'source' field of emitted events.
        """

        super().__init__()

        api_key = os.getenv("DG_API_KEY")
        if api_key is None:
            raise RuntimeError("DG_API_KEY is not set")

        self.client = DeepgramClient(api_key)
        self.conn = None
        self.language = language
        self.diarize = diarize
        self.label = label

    async def act(self, event):
        """Take any event as the trigger to start listening. Once a connection
        is established, ignore any further event's reading as trigger.
        """

        if self.conn:
            return

        async def on_error(_self, error, **kwargs):
            logger.error(kwargs["error"])

        async def on_message(_self, result, **kwargs):
            alt = result.channel.alternatives[0]
            if len(alt.transcript) == 0:
                return

            for word in alt.words:
                await self.emit(make_event(BusType.Texts, {
                    "source": self.label,
                    "speaker": word.speaker if self.diarize else None,
                    "text": word.punctuated_word,
                    "is_final": result.is_final,
                    "start": word.start,
                    "end": word.end,
                    "confidence": word.confidence
                }))

        async def on_metadata(_self, metadata, **kwargs):
            logger.debug(metadata)

        async def on_speech_started(_self, speech_started, **kwargs):
            logger.debug(speech_started)

        async def on_utterance_end(_self, utterance_end, **kwargs):
            await self.emit(make_event(BusType.Semantics, {
                "source": self.label,
                "signal": "eou",
            }))

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
