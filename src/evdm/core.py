"""Event bus related core functions."""

import asyncio
from enum import Enum
import itertools

from dataclasses import dataclass
from datetime import datetime
from abc import abstractmethod, ABC
from typing import Awaitable, Callable


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
    bus: BusType
    created_on: datetime
    data: dict


def make_event(bus: BusType, data: dict) -> Event:
    return Event(bus, datetime.now(), data)


class Actor(ABC):
    """Abstract Actor class.

    An actor subscribes for events from a bus and does some processing,
    possibly resulting in emitting events to other buses.
    """

    @abstractmethod
    async def act(self, event: Event):
        """Take `event` and do something with it.

        After the compute is finished, optionally use self.emit to emit more messages.
        """
        raise NotImplementedError()

    async def close(self):
        """Shutdown sequence that's executed when the bus is closed."""
        pass


class Emitter:
    """
    Mixin for emitter actors.
    """

    def __init__(self) -> None:
        self.emit: Callable[[Event], Awaitable]


class HEB:
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

    async def emit(self, event: Event):
        """Push `event` on the bus.

        This is supposed to be called by actors whenever they want to emit any
        event to the bus. As of now there is no buffer and every `put`
        immediately passes the event to listening actors so they can act on it.
        """

        for listener in self.listeners[event.bus]:
            task = asyncio.create_task(listener.act(event))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def trigger(self, bus: BusType):
        """
        Generate a dummy trigger event on a bus.
        """

        await self.emit(make_event(bus, {}))

    def register(self, actor: "Actor", listen_on: BusType):
        """Register `actor` to listen on all events that come on given bus."""

        self.listeners[listen_on].append(actor)
        if isinstance(actor, Emitter):
            actor.emit = self.emit

    @property
    def actors(self) -> list:
        return list(itertools.chain(*self.listeners.values()))

    async def close(self):
        """Wait for all background tasks to finish before exiting."""

        await asyncio.gather(*self._background_tasks)
        await asyncio.gather(*(a.close() for a in self.actors))
