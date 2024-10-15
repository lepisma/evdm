# evdm

![GitHub Tag](https://img.shields.io/github/v/tag/lepisma/evdm)

Prototype of a [Hierarchical Event
Bus](https://lepisma.xyz/2024/08/01/hierarchical-event-bus-for-spoken-conversational-systems/index.html)
for building event driven speech conversational AI systems. Read the linked blog
for more details.

Although it's very simple and direct, you can play around with an example
voicebot built using OpenAI's realtime API in the `./scripts/` directory. After
`uv install`, run `uv run python ./scripts/example-oai-realtime.py`. Echo
cancellation is not available yet so you should run this example with headphones
on. Another example (`example-multi-speaker.py`) is a multi user voicebot that
can handle talking to multiple speakers.
