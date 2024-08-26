"""In build actors with focus on Spoken Dialog Systems."""

from abc import abstractmethod, ABC
from evdm.events import Event


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
