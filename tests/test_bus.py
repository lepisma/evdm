from evdm.core import HEB, BusType, make_event, Actor, Emitter
import asyncio
import pytest


class Incrementor(Actor, Emitter):
    """Listens to devices bus for number, increments and puts on text bus. Also
    passes on to the memory bus."""

    async def act(self, event):
        num = event.data.get("number", None)
        if num is not None:
            await self.emit(make_event(BusType.Texts, {"number": num + 1}))


class Tap(Actor):
    def __init__(self) -> None:
        super().__init__()
        self.items = []

    async def act(self, event):
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
        await heb.emit(make_event(BusType.Devices, {"number": i}))

    await heb.close()
    assert tap.items == [i + 1 for i in range(5)]
