from evdm.bus import HEB, Actor, BusType
from evdm.events import Event, make_event
import asyncio

heb = HEB()

class Accumulator(Actor):
    """Listens to memory bus and adds up all the incoming numbers.

    At every multiple of 10 in the memory, emit an event on text bus.
    """

    def __init__(self) -> None:
        self.memory = 0

    async def act(self, event: Event, heb: HEB):
        self.memory += event.data.get("number", 0)

        if self.memory % 10 == 0:
            await heb.put(make_event({"text": f"Memory at {self.memory}"}), BusType.Texts)


class Incrementor(Actor):
    """Listens to devices bus for number, increments and puts on text bus. Also
    passes on to the memory bus."""

    async def act(self, event, heb):
        num = event.data.get("number", None)
        if num is not None:
            await heb.put(make_event({"text": num + 1}), BusType.Texts)
            await heb.put(make_event({"number": num}), BusType.Memory)


class Printer(Actor):
    """Listens to text bus and prints the messages."""

    async def act(self, event, heb):
        print(event)


heb.register(Accumulator(), listen_on=BusType.Memory)
heb.register(Incrementor(), listen_on=BusType.Devices)
heb.register(Printer(), listen_on=BusType.Texts)

async def main():
    for i in range(10):
        await asyncio.sleep(0.4)
        await heb.put(make_event({"number": i}), BusType.Devices)

    await heb.close()

asyncio.run(main())
