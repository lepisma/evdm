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

    def __init__(self) -> None:
        self.sr = 48_000

    async def act(self, event, heb):
        q = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _callback(indata, frame_count, time_info, status):
            loop.call_soon_threadsafe(q.put_nowait, (indata.copy(), status))

        stream = sd.InputStream(callback=_callback, channels=1)

        with stream:
            while True:
                indata, status = await q.get()
                await heb.put(make_event({
                    "source": "microphone",
                    "samples": indata,
                    "sr": self.sr
                }), BusType.AudioSignals)

