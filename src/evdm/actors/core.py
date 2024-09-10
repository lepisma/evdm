"""Base actors and utilities."""

from abc import abstractmethod, ABC
from evdm.bus import BusType
from evdm.events import Event

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
