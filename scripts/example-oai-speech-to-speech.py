"""
Example script that uses OpenAI realtime API to build a simple, at the moment,
half duplex voicebot
"""

from evdm.actors.audio import MicrophoneListener, SpeakerPlayer
from evdm.actors.conversation import OpenAISpeechtoSpeechConvAgent
from evdm.core import HEB, BusType
import asyncio


async def main():
    heb = HEB()

    mic = MicrophoneListener(chunk_size=100, samplerate=24_000)
    agent = OpenAISpeechtoSpeechConvAgent("You are a helpful agent", source="microphone")
    await agent.connect()

    speaker = SpeakerPlayer(source="oai-realtime")

    heb.register(mic, listen_on=BusType.Devices)
    heb.register(agent, listen_on=BusType.AudioSignals)
    heb.register(speaker, listen_on=BusType.AudioSignals)

    await heb.trigger(BusType.Devices)
    await heb.close()

asyncio.run(main())
