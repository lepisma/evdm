"""In built actors with focus on Spoken Dialog Systems."""

from abc import abstractmethod, ABC
from evdm.bus import BusType
from evdm.events import Event, make_event
import numpy as np
import sounddevice as sd
import asyncio

from loguru import logger


class Actor(ABC):
    """Abstract Actor class.

    An actor subscribes for events from a bus and does some processing,
    possibly resulting in emitting events to other buses.
    """

    @abstractmethod
    async def act(self, event: Event, heb: "HEB"):
        """Take `event` and do something with it.

        After the compute is finished, optionally use heb to emit more messages.
        """
        raise NotImplementedError()


class DebugTap(Actor):
    """Actor that reads events on a bus and logs events at DEBUG level."""

    def __init__(self, bus: BusType) -> None:
        super().__init__()
        self.bus = bus

    async def act(self, event, heb):
        logger.debug(f"{event} on {self.bus}")


class MicrophoneListener(Actor):
    """Actor that reads audio chunks from microphone directly (not via Device
    bus) and puts events on the AudioSignals bus.
    """

    def __init__(self, chunk_size: int = 50) -> None:
        """`chunk_size` tells the size of each emitted chunk in ms. You could
        get a lower sized chunk when the source has stopped emitting audio.
        """
        self.sr = 48_000
        self.chunk_size = chunk_size

    async def act(self, event, heb):
        q = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _callback(indata, frame_count, time_info, status):
            loop.call_soon_threadsafe(q.put_nowait, (indata.copy(), status))

        stream = sd.InputStream(
            callback=_callback,
            channels=1,
            blocksize=int((self.chunk_size / 1000) * self.sr)
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

    def __init__(self) -> None:
        self.sr = None

    async def act(self, event, heb):
        """
        Event's `data` structure is like the following:

        - `source`: Label for the source of this event.
        - `samples`: np.ndarray containing the audio samples.
        - `sr`: Sampling rate of the audio data.
        """

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
            channels=1
        )

        with stream:
            await ev.wait()
