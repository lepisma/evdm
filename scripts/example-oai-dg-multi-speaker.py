"""Example script that shows multiple people talking to an LLM voicebot. It uses
Deepgram for diarized audio transcription and OpenAI realtime API for dialog
management and speech synthesis.
"""

from evdm.actors.audio import DeepgramTranscriber, SpeakerPlayer
from evdm.actors.conversation import OpenAITexttoSpeechConvAgent
from evdm.core import HEB, BusType, make_event
import asyncio


async def main():
    heb = HEB()

    dg = DeepgramTranscriber("en-IN", diarize=True)
    oai = OpenAITexttoSpeechConvAgent("You are a helpful agent. You will be talking to 1 or more people whose utterances will be prefixed with 'speaker <id>'.", "deepgram")
    await oai.connect()

    speaker = SpeakerPlayer(source="bot:oai-realtime")

    heb.register(dg, listen_on=BusType.Devices)
    heb.register(oai, listen_on=BusType.Texts)
    heb.register(oai, listen_on=BusType.Semantics)
    heb.register(speaker, listen_on=BusType.AudioSignals)

    await heb.emit(make_event(BusType.Devices, {}))

    try:
        while True:
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        await heb.close()

asyncio.run(main())
