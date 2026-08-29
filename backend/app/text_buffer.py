SENTENCE_ENDERS = {".", "!", "?", "\n"}
MAX_BUFFER_CHARS = 200


class SentenceBuffer:
    def __init__(self, on_chunk_ready):
        self.buffer = ""
        self.on_chunk_ready = on_chunk_ready
        self.in_think_block = False

    async def add(self, token):
        text = token

        if "<think>" in text:
            self.in_think_block = True
            text = text.split("<think>")[0]

        if "</think>" in text:
            self.in_think_block = False
            text = text.split("</think>")[-1]

        if self.in_think_block:
            return

        self.buffer += text

        if self.buffer and self.buffer[-1] in SENTENCE_ENDERS or len(self.buffer) >= MAX_BUFFER_CHARS:
            await self._flush()

    async def _flush(self):
        text = self.buffer.strip()
        self.buffer = ""
        if text:
            await self.on_chunk_ready(text)

    async def flush_remaining(self):
        await self._flush()