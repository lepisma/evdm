from evdm.bus import HEB, BusType, make_event
from evdm.actors.core import Actor
import asyncio
import pytest


class Incrementor(Actor):
    """Listens to devices bus for number, increments and puts on text bus. Also
    passes on to the memory bus."""

    async def act(self, event, heb):
        num = event.data.get("number", None)
        if num is not None:
            await heb.put(make_event({"number": num + 1}), BusType.Texts)


class Tap(Actor):
    def __init__(self) -> None:
        super().__init__()
        self.items = []

    async def act(self, event, heb):
        num = event.data.get("number")
        self.items.append(num)


@pytest.mark.asyncio
async def test_basic_bus_execution():
    heb = HEB()
    tap = Tap()

    heb.register(Incrementor(), listen_on=BusType.Devices)
    heb.register(tap, listen_on=BusType.Texts)

    for i in range(5):
        await asyncio.sleep(0.1)
        await heb.put(make_event({"number": i}), BusType.Devices)

    await heb.close()
    assert tap.items == [i + 1 for i in range(5)]
