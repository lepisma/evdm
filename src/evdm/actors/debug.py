from evdm.core import Actor

from loguru import logger


class DebugTap(Actor):
    """Actor that reads events on a bus and logs events at DEBUG level."""

    async def act(self, event):
        logger.debug(f"[{event.bus}]: {event}")
