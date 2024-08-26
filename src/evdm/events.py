from dataclasses import dataclass
from datetime import datetime


@dataclass
class Event:
    """Event that runs on the buses."""
    created_on: datetime
    data: dict


def make_event(data: dict) -> Event:
    return Event(datetime.now(), data)
