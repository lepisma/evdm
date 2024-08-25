from evdm.bus import HEB, Actor, Event, BusType, make_event
import asyncio

heb = HEB()

class Dummy(Actor):
    async def act(self, event: Event, heb: HEB):
        await asyncio.sleep(1.0)
        await heb.put(make_event({"text": "hi"}), BusType.Texts)

dummy = Dummy()

heb.register(dummy, listen_on=BusType.AudioSegments)

async def main():
    for _ in range(10):
        await asyncio.sleep(0.4)
        await heb.put(make_event({"data": None}), BusType.AudioSegments)

asyncio.run(main())
