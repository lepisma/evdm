"""In built actors with focus on Spoken Dialog Systems."""

from evdm.bus import BusType
from evdm.events import make_event
from evdm.actors.core import Actor
import sounddevice as sd
import asyncio


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

    async def act(self, event, heb):
        """
        Event's `data` structure is like the following:

        - `source`: Label for the source of this event.
        - `samples`: np.ndarray containing the audio samples.
        - `sr`: Sampling rate of the audio data.
        """

        if event.data["source"] != self.source:
            return

        loop = asyncio.get_event_loop()
        ev = asyncio.Event()
        idx = 0

        self.sr = event.data["sr"]
        samples = event.data["samples"]

        def _callback(outdata, frame_count, time_info, status):
            nonlocal idx
            remainder = len(samples) - idx
            if remainder == 0:
                loop.call_soon_threadsafe(ev.set)
                raise sd.CallbackStop
            valid_frames = frame_count if remainder >= frame_count else remainder
            outdata[:valid_frames] = samples[idx:idx + valid_frames]
            outdata[valid_frames:] = 0
            idx += valid_frames

        stream = sd.OutputStream(
            callback=_callback,
            channels=1,
            samplerate=self.sr
        )

        with stream:
            await ev.wait()
