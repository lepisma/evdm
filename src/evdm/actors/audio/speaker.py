from evdm.core import Actor
from collections import deque
import asyncio
import sounddevice as sd
import numpy as np


class SpeakerPlayer(Actor):
    """Play audio from AudioSignals bus directly (without involving device bus)
    without buffering.
    """

    def __init__(self, source: str) -> None:
        """Only play audio from the given `source` name on Audio Signals bus.
        """
        super().__init__()
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

    async def act(self, event):
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
