import json
import asyncio
import websockets
from app.config import DEEPGRAM_API_KEY, DEEPGRAM_STT_MODEL

DEEPGRAM_STT_URL = (
    f"wss://api.deepgram.com/v1/listen?model={DEEPGRAM_STT_MODEL}"
    "&encoding=linear16&sample_rate=16000&interim_results=true"
    "&endpointing=800&punctuate=true&vad_events=true"
)


class DeepgramSTT:
    def __init__(self, on_transcript, on_error=None, on_speech_started=None):
        self.on_transcript = on_transcript
        self.on_error = on_error
        self.on_speech_started = on_speech_started
        self.ws = None
        self._listen_task = None

    async def connect(self):
        try:
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    DEEPGRAM_STT_URL,
                    additional_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
                ),
                timeout=5,
            )
        except Exception as e:
            print(f"STT connect failed: {e}")
            if self.on_error:
                await self.on_error("stt_connect_failed")
            return
        self._listen_task = asyncio.create_task(self._listen())

    async def send_audio(self, chunk: bytes):
        if not self.ws:
            return
        try:
            await self.ws.send(chunk)
        except websockets.exceptions.ConnectionClosed:
            if self.on_error:
                await self.on_error("stt_disconnected")

    async def _listen(self):
        try:
            async for message in self.ws:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "SpeechStarted":
                    if self.on_speech_started:
                        await self.on_speech_started()
                    continue

                alt = data.get("channel", {}).get("alternatives", [{}])[0]
                transcript = alt.get("transcript", "")
                if not transcript.strip():
                    continue
                is_final = data.get("is_final", False)
                await self.on_transcript(transcript, is_final)
        except websockets.exceptions.ConnectionClosed:
            if self.on_error:
                await self.on_error("stt_disconnected")

    async def close(self):
        if self._listen_task:
            self._listen_task.cancel()
        if self.ws:
            await self.ws.close()