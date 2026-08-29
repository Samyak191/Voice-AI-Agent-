import json
import asyncio
import random
import websockets
from app.config import (
    DEEPGRAM_API_KEY,
    DEEPGRAM_TTS_MODEL,
    SIMULATE_SLOW_TTS,
    SLOW_TTS_DELAY_SECONDS,
    SIMULATE_DUPLICATE_CHUNKS,
)

DEEPGRAM_TTS_URL = (
    f"wss://api.deepgram.com/v1/speak?model={DEEPGRAM_TTS_MODEL}"
    "&encoding=linear16&sample_rate=24000"
)


class DeepgramTTS:
    def __init__(self, on_audio_chunk, on_error=None):
        self.on_audio_chunk = on_audio_chunk
        self.on_error = on_error
        self.ws = None
        self._listen_task = None
        self._worker_task = None
        self._seq = 0
        self._queue = asyncio.Queue()
        self._pending_flushes = 0
        self._all_flushed = asyncio.Event()
        self._all_flushed.set()
        self._no_more_input = asyncio.Event()

    async def connect(self):
        try:
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    DEEPGRAM_TTS_URL,
                    additional_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
                ),
                timeout=5,
            )
        except Exception as e:
            if self.on_error:
                await self.on_error("tts_connect_failed")
            return
        self._listen_task = asyncio.create_task(self._listen())
        self._worker_task = asyncio.create_task(self._worker())

    async def speak(self, text):
        await self._queue.put(text)

    def mark_no_more_input(self):
        self._no_more_input.set()

    async def wait_until_done(self, timeout=20):
        await self._no_more_input.wait()
        await self._queue.join()
        try:
            await asyncio.wait_for(self._all_flushed.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    async def _worker(self):
        while True:
            text = await self._queue.get()
            if text is None:
                self._queue.task_done()
                break
            await self._send_one(text)
            self._queue.task_done()

    async def _send_one(self, text):
        if not self.ws:
            return

        if SIMULATE_SLOW_TTS and random.random() < 0.3:
            await asyncio.sleep(SLOW_TTS_DELAY_SECONDS)

        try:
            self._pending_flushes += 1
            self._all_flushed.clear()
            await asyncio.wait_for(
                self.ws.send(json.dumps({"type": "Speak", "text": text})),
                timeout=8,
            )
            await self.ws.send(json.dumps({"type": "Flush"}))
        except Exception as e:
            self._pending_flushes = max(0, self._pending_flushes - 1)
            if self._pending_flushes == 0:
                self._all_flushed.set()
            if self.on_error:
                await self.on_error("tts_request_failed")

    async def _listen(self):
        try:
            async for message in self.ws:
                if isinstance(message, bytes):
                    self._seq += 1
                    await self.on_audio_chunk(message, self._seq)

                    if SIMULATE_DUPLICATE_CHUNKS and self._seq % 4 == 0:
                        await self.on_audio_chunk(message, self._seq)
                else:
                    data = json.loads(message)
                    if data.get("type") == "Flushed":
                        self._pending_flushes = max(0, self._pending_flushes - 1)
                        if self._pending_flushes == 0:
                            self._all_flushed.set()
        except websockets.exceptions.ConnectionClosed:
            if self.on_error:
                await self.on_error("tts_disconnected")

    async def clear(self):
        if self.ws:
            await self.ws.send(json.dumps({"type": "Clear"}))

    async def close(self):
        await self._queue.put(None)
        if self._listen_task:
            self._listen_task.cancel()
        if self._worker_task:
            self._worker_task.cancel()
        if self.ws:
            await self.ws.close()