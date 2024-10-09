"""Actors related to conversation management."""

from evdm.actors.core import Actor
from evdm.bus import BusType
from evdm.events import Event, make_event
import ollama


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
