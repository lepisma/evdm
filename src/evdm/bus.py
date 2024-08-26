"""Event bus related functions."""

from enum import Enum
from abc import abstractmethod, ABC
import asyncio
from dataclasses import dataclass
from loguru import logger
from datetime import datetime


class BusType(Enum):
    """Bus types for a Spoken Dialog System."""

    Memory = 1
    Semantics = 2
    Texts = 3
    AudioSegments = 4
    AudioSignals = 5
    Devices = 6


@dataclass
class Event:
    """Event that runs on the buses."""
    created_on: datetime
    data: dict


def make_event(data: dict) -> Event:
    return Event(datetime.now(), data)


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


class HEB:
    """Heirarchical Event Bus."""

    def __init__(self):
        """Initialize buses and callbacks."""
        self.listeners: dict[BusType, list[Actor]] = {
            BusType.Memory: [],
            BusType.Semantics: [],
            BusType.Texts: [],
            BusType.AudioSegments: [],
            BusType.AudioSignals: [],
            BusType.Devices: []
        }

        self._background_tasks: set[asyncio.Task] = set()

    async def put(self, event: Event, bus: BusType):
        """Push `event` on the bus.

        This is supposed to be called by actors whenever they want to emit any
        event to the bus. As of now there is no buffer and every `put`
        immediately passes the event to listening actors so they can act on it.
        """
        logger.debug(f"{event} on {bus}")

        for listener in self.listeners[bus]:
            task = asyncio.create_task(listener.act(event, self))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    def register(self, actor: Actor, listen_on: BusType):
        """Register `actor` to listen on all events that come on given bus."""

        self.listeners[listen_on].append(actor)

    async def close(self):
        """Wait for all background tasks to finish before exiting."""

        await asyncio.gather(*self._background_tasks)
