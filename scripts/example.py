from evdm.core import HEB, BusType, Event, make_event, Actor, Emitter
import asyncio


class Accumulator(Actor, Emitter):
    """Listens to memory bus and adds up all the incoming numbers.

    At every multiple of 10 in the memory, emit an event on text bus.
    """

    def __init__(self) -> None:
        self.memory = 0

    async def act(self, event: Event):
        self.memory += event.data.get("number", 0)

        if self.memory % 10 == 0:
            await self.emit(make_event(BusType.Texts, {"text": f"Memory at {self.memory}"}))


class Incrementor(Actor, Emitter):
    """Listens to devices bus for number, increments and puts on text bus. Also
    passes on to the memory bus."""

    async def act(self, event):
        num = event.data.get("number", None)
        if num is not None:
            await self.emit(make_event(BusType.Texts, {"text": num + 1}))
            await self.emit(make_event(BusType.Memory, {"number": num}))


class Printer(Actor):
    """Listens to text bus and prints the messages."""

    async def act(self, event):
        print(event)


heb = HEB()
heb.register(Accumulator(), listen_on=BusType.Memory)
heb.register(Incrementor(), listen_on=BusType.Devices)
heb.register(Printer(), listen_on=BusType.Texts)

async def main():
    for i in range(10):
        await asyncio.sleep(0.4)
        await heb.emit(make_event(BusType.Devices, {"number": i}))

    await heb.close()

asyncio.run(main())
