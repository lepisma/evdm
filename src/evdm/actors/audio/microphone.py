from evdm.core import Actor, Emitter, make_event, BusType
import asyncio
import sounddevice as sd


class MicrophoneListener(Actor, Emitter):
    """Actor that reads audio chunks from microphone directly (not via Device
    bus) and puts events on the AudioSignals bus.
    """

    def __init__(self, chunk_size: int = 50, samplerate: int = 48_000) -> None:
        """`chunk_size` tells the size of each emitted chunk in ms. You could
        get a lower sized chunk when the source has stopped emitting audio.
        """
        super().__init__()

        self.sr = samplerate
        self.chunk_size = chunk_size

    async def act(self, event):
        q = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _callback(indata, frame_count, time_info, status):
            loop.call_soon_threadsafe(q.put_nowait, (indata.copy(), status))

        stream = sd.InputStream(
            callback=_callback,
            channels=1,
            blocksize=int((self.chunk_size / 1000) * self.sr),
            samplerate=self.sr
        )

        with stream:
            while True:
                indata, _ = await q.get()
                await self.emit(make_event(BusType.AudioSignals, {
                    "source": "microphone",
                    "samples": indata,
                    "sr": self.sr
                }))
