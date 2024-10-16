"""Actors related to conversation management."""

import asyncio

from evdm.actors.core import Actor
from evdm.bus import BusType, Event, make_event
import ollama
import os
import json
from websockets.asyncio.client import connect
from loguru import logger
import soundfile as sf
import io
import numpy as np
import base64


class OpenAITexttoSpeechConvAgent(Actor):
    """Agent that uses OpenAI Realtime API for multi-party conversations by
    sending text from user side and receiving audio from OpenAI.
    """

    def __init__(self, prompt: str, source: str) -> None:
        super().__init__()
        self.prompt = prompt
        self.source = source

        # Reference to the heb for emitting events. This is set at the first
        # call to `act`.
        self.heb = None
        self.accumulator = []

    async def connect(self):
        self.ws = await self._connect()
        await self._set_prompt()
        asyncio.create_task(self._handle_server_events())

    async def _connect(self):
        url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
        api_key = os.getenv("OPENAI_API_KEY")

        if api_key is None:
            raise ValueError("OPENAI_API_KEY not set.")

        return await connect(url, additional_headers={
            "Authorization": "Bearer " + api_key,
            "OpenAI-Beta": "realtime=v1"
        })

    async def _set_prompt(self):
        await self.ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": self.prompt,
                "voice": "alloy",
                "output_audio_format": "pcm16",
                "tools": [],
                "tool_choice": "none",
                "temperature": 0.8
            }
        }))

    async def _handle_server_events(self):
        """Loop and listen to server events and then act accordingly. We ignore
        most of the events for now but we still 'handle' all to ensure that any
        upstream change doesn't blow up in our face.
        """

        async for message in self.ws:
            data = json.loads(message)

            match data["type"]:
                case "error":
                    await self.handle_error(data)
                case "session.created":
                    logger.debug("Session created.")
                case "session.updated":
                    pass
                case "conversation.created":
                    pass
                case "input_audio_buffer.committed":
                    pass
                case "input_audio_buffer.cleared":
                    pass
                case "input_audio_buffer.speech_started":
                    logger.debug("Input speech started")
                case "input_audio_buffer.speech_stopped":
                    logger.debug("Input speech stopped")
                case "conversation.item.created":
                    logger.debug("Conversation item created")
                case "conversation.item.input_audio_transcription.completed":
                    pass
                case "conversation.item.input_audio_transcription.failed":
                    pass
                case "conversation.item.truncated":
                    pass
                case "conversation.item.deleted":
                    pass
                case "response.created":
                    logger.debug(f"Response created")
                case "response.done":
                    logger.debug(f"Response done")
                case "response.output_item.added":
                    logger.debug(f"Response item added")
                case "response.output_item.done":
                    logger.debug(f"Response item done")
                case "response.content_part.added":
                    pass
                case "response.content_part.done":
                    pass
                case "response.text.delta":
                    pass
                case "response.text.done":
                    await self.handle_output_text(data)
                case "response.audio_transcript.delta":
                    pass
                case "response.audio_transcript.done":
                    await self.handle_output_transcript(data)
                case "response.audio.delta":
                    await self.handle_audio_delta(data)
                case "response.audio.done":
                    pass
                case "response.function_call_arguments.delta":
                    pass
                case "response.function_call_arguments.done":
                    pass
                case "rate_limits.updated":
                    pass

    async def handle_error(self, message_data: dict):
        raise RuntimeError(f"Server error: {message_data}")

    async def handle_output_text(self, message_data: dict):
        await self.heb.put(make_event({
            "source": "bot:oai-realtime",
            "text": message_data["text"],
            "is_eou": True
        }), BusType.Texts)

    async def handle_output_transcript(self, message_data: dict):
        await self.heb.put(make_event({
            "source": "bot:oai-realtime-transcript",
            "text": message_data["transcript"],
            "is_eou": True
        }), BusType.Texts)

    async def handle_audio_delta(self, message_data: dict):
        samples, sr = await self.decode_audio(message_data["delta"])

        await self.heb.put(make_event({
            "source": "bot:oai-realtime", "samples": samples, "sr": sr
        }), BusType.AudioSignals)

    async def decode_audio(self, data: str):
        """Decode base64 audio `data` that's in raw PCM_16 little endian format
        to samples and sampling rate."""

        # This is the default for the API
        sr = 24_000

        binary_data = base64.b64decode(data)

        def _read(buffer):
            with sf.SoundFile(buffer, "r", format="RAW", samplerate=sr, channels=1, subtype="PCM_16", endian="LITTLE") as fp:
                return fp.read()

        with io.BytesIO(binary_data) as buffer:
            loop = asyncio.get_event_loop()
            samples = await loop.run_in_executor(None, lambda: _read(buffer))

        samples = samples.astype(np.float32)
        return samples.reshape(len(samples), 1) , sr

    def build_diarized_transcript(self, data_items: list[dict]) -> str:
        # First we figure out if diarization is present
        single_speaker = data_items[0]["source"] == self.source

        if single_speaker:
            return " ".join([it["text"] for it in data_items])

        # HACK: This way of tagging speakers will change
        last_speaker = int(data_items[0]["source"].split(":spk")[1])

        lines = []
        accumulator = []

        for it in data_items:
            current_speaker = int(it["source"].split(":spk")[1])
            if current_speaker == last_speaker:
                accumulator.append(it["text"])
            else:
                lines.append(f"speaker {last_speaker + 1}: {' '.join(accumulator)}")
                accumulator = [it["text"]]
                last_speaker = current_speaker

        lines.append(f"speaker {last_speaker + 1}: {' '.join(accumulator)}")

        return "\n".join(lines)

    async def act(self, event: Event, heb):
        if not event.data["source"].startswith(self.source):
            return

        if self.heb is None:
            self.heb = heb

        if "signal" in event.data:
            if event.data["signal"] == "eou":
                transcript = self.build_diarized_transcript(self.accumulator)
                self.accumulator = []

                await self.ws.send(json.dumps({
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": transcript
                            }
                        ]
                    }
                }))

                await self.ws.send(json.dumps({
                    "type": "response.create"
                }))

        else:
            self.accumulator.append(event.data)


class OpenAISpeechtoSpeechConvAgent(Actor):
    """Agent that uses OpenAI Realtime API for two-party conversations.

    This listens on Audio Signals bus (since we use server VAD mode from the
    API) and emits to Audio Signals (output audio) and Lexical Segments
    (transcripts) bus.

    """

    def __init__(self, prompt: str, source: str) -> None:
        super().__init__()
        self.prompt = prompt
        self.source = source

        # Reference to the heb for emitting events. This is set at the first
        # call to `act`.
        self.heb = None

    async def connect(self):
        self.ws = await self._connect()
        await self._set_prompt()
        asyncio.create_task(self._handle_server_events())

    async def _connect(self):
        url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
        api_key = os.getenv("OPENAI_API_KEY")

        if api_key is None:
            raise ValueError("OPENAI_API_KEY not set.")

        return await connect(url, additional_headers={
            "Authorization": "Bearer " + api_key,
            "OpenAI-Beta": "realtime=v1"
        })

    async def _set_prompt(self):
        await self.ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": self.prompt,
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 200
                },
                "tools": [],
                "tool_choice": "none",
                "temperature": 0.8
            }
        }))

    async def _handle_server_events(self):
        """Loop and listen to server events and then act accordingly. We ignore
        most of the events for now but we still 'handle' all to ensure that any
        upstream change doesn't blow up in our face.
        """

        async for message in self.ws:
            data = json.loads(message)

            match data["type"]:
                case "error":
                    await self.handle_error(data)
                case "session.created":
                    logger.debug("Session created.")
                case "session.updated":
                    pass
                case "conversation.created":
                    pass
                case "input_audio_buffer.committed":
                    pass
                case "input_audio_buffer.cleared":
                    pass
                case "input_audio_buffer.speech_started":
                    logger.debug("Input speech started")
                case "input_audio_buffer.speech_stopped":
                    logger.debug("Input speech stopped")
                case "conversation.item.created":
                    pass
                case "conversation.item.input_audio_transcription.completed":
                    await self.handle_input_transcript(data)
                case "conversation.item.input_audio_transcription.failed":
                    pass
                case "conversation.item.truncated":
                    pass
                case "conversation.item.deleted":
                    pass
                case "response.created":
                    pass
                case "response.done":
                    pass
                case "response.output_item.added":
                    pass
                case "response.output_item.done":
                    pass
                case "response.content_part.added":
                    pass
                case "response.content_part.done":
                    pass
                case "response.text.delta":
                    pass
                case "response.text.done":
                    await self.handle_output_text(data)
                case "response.audio_transcript.delta":
                    pass
                case "response.audio_transcript.done":
                    await self.handle_output_transcript(data)
                case "response.audio.delta":
                    await self.handle_audio_delta(data)
                case "response.audio.done":
                    pass
                case "response.function_call_arguments.delta":
                    pass
                case "response.function_call_arguments.done":
                    pass
                case "rate_limits.updated":
                    pass

    async def handle_error(self, message_data: dict):
        raise RuntimeError(f"Server error: {message_data}")

    async def handle_output_text(self, message_data: dict):
        await self.heb.put(make_event({
            "source": "bot:oai-realtime",
            "text": message_data["text"],
            "is_eou": True
        }), BusType.Texts)

    async def handle_output_transcript(self, message_data: dict):
        await self.heb.put(make_event({
            "source": "bot:oai-realtime-transcript",
            "text": message_data["transcript"],
            "is_eou": True
        }), BusType.Texts)

    async def handle_input_transcript(self, message_data: dict):
        await self.heb.put(make_event({
            "source": "user",
            "text": message_data["transcript"],
            "is_eou": True
        }), BusType.Texts)

    async def handle_audio_delta(self, message_data: dict):
        samples, sr = await self.decode_audio(message_data["delta"])

        await self.heb.put(make_event({
            "source": "bot:oai-realtime", "samples": samples, "sr": sr
        }), BusType.AudioSignals)

    async def encode_audio(self, audio_samples, samplerate: int) -> str:
        """Encode audio to base64 encoded binary format that's acceptable via
        the API.
        """

        # HACK since they are allowing only this sampling rate right now
        assert samplerate == 24_000

        def _write(buffer, samples, sr: int):
            with sf.SoundFile(buffer, "w", format="RAW", samplerate=sr, channels=1, subtype="PCM_16", endian="LITTLE") as fp:
                fp.write(samples)

        with io.BytesIO() as buffer:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: _write(buffer, audio_samples, samplerate))

            buffer.seek(0)
            return base64.b64encode(buffer.read()).decode("utf-8")

    async def decode_audio(self, data: str):
        """Decode base64 audio `data` that's in raw PCM_16 little endian format
        to samples and sampling rate."""

        # This is the default for the API
        sr = 24_000

        binary_data = base64.b64decode(data)

        def _read(buffer):
            with sf.SoundFile(buffer, "r", format="RAW", samplerate=sr, channels=1, subtype="PCM_16", endian="LITTLE") as fp:
                return fp.read()

        with io.BytesIO(binary_data) as buffer:
            loop = asyncio.get_event_loop()
            samples = await loop.run_in_executor(None, lambda: _read(buffer))

        samples = samples.astype(np.float32)
        return samples.reshape(len(samples), 1) , sr

    async def act(self, event: Event, heb):
        if event.data["source"] != self.source:
            return

        if self.heb is None:
            self.heb = heb

        sr = event.data["sr"]
        samples = event.data["samples"]

        encoded_audio = await self.encode_audio(samples, sr)

        await self.ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": encoded_audio
        }))


class BackchannelDetectorAgent(Actor):
    """Agent that detects backchannel events on text bus and emits on semantics bus.
    """

    def __init__(self) -> None:
        super().__init__()

    async def act(self, event: Event, heb):
        """There are the following kinds of backchannels that this detects (per speaker):

        1. Interruptions that need the current speaker to yield.

        2. Background events that need to be acknowledged but don't need to be
           read as interruptions. They could be read as things that we need to do.

        """

        # Detect who all is currently speaking
        # Run the detector on the partial text
        # Emit the backchannel prediction on semantic bus
        # This is complete specification for this actor

        pass


class ConversationalMemory(Actor):
    """Memory for all conversation events. This saves all events from semantic
    bus and superset utterances from text bus."""

    def __init__(self) -> None:
        super().__init__()

    async def act(self, event: Event, heb):
        pass


class LLMConversationAgent(Actor):
    """
    LLM Conversational Agent that responds to events from text bus.
    """

    def __init__(self, prompt = None) -> None:
        super().__init__()
        self.prompt = prompt or ("You are a helpful conversational agent. "
                       "You will be given history of utterances prefixed with name "
                       "of the speaker like `speaker:` and you have to respond with "
                       "`bot:` prefix. Keep the responses short and conversational.")
        self.history: list[ollama.Message] = []
        self.model = "gemma2:2b"

    async def act(self, event: Event, heb):
        """Structure of `event.data`:

        - `source`: Label for the speaker
        - `text`: Text string from the utterance
        - `is-eou`: Whether this is an end of utterance
        """

        # Listen to semantic bus
        #
        # If you are speaking and an interruption comes, stop (this agent is
        # polite that way). This is only detected from the semantic bus and not
        # via regular text bus.

        # Don't act on partial utterances for now
        if not event.data["is-eou"]:
            return

        # Only act on user utterances for now, ignoring distinction among users
        if event.data["source"].startswith("bot:"):
            return

        speaker_name = "speaker"
        llm_input = f"{speaker_name}: {event.data['text']}"
        self.history.append({"role": "user", "content": llm_input})

        client = ollama.AsyncClient()

        accumulated_text: list[str] = []
        async for part in await client.chat(
                model=self.model,
                messages=[
                    ollama.Message(role="assistant", content=self.prompt),
                ] + self.history,
                stream=True
        ):
            accumulated_text.append(part["message"]["content"])

            if part["done"]:
                self.history.append({"role": "assistant", "content": "".join(accumulated_text)})
                accumulated_text = []

            await heb.put(make_event({
                "source": "bot:ollama",
                "is-eou": part["done"],
                "text": "".join(accumulated_text)
            }), BusType.Texts)
