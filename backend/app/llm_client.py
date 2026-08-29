import json
import httpx
from app.config import GROQ_API_KEY, GROQ_LLM_MODEL

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


async def stream_llm_response(history, on_token, generation, is_current, on_error=None):
    payload = {
        "model": GROQ_LLM_MODEL,
        "messages": history,
        "stream": True,
        "reasoning_effort": "none",
        "max_tokens": 200,
        "temperature": 0.7,
        "top_p": 0.8,
        "presence_penalty": 1.5,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    full_text = ""

    try:
        async with httpx.AsyncClient(timeout=40) as client:
            async with client.stream("POST", GROQ_URL, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    if on_error:
                        await on_error("llm_bad_response")
                    return full_text

                async for line in response.aiter_lines():
                    if not is_current(generation):
                        break

                    if not line.startswith("data: "):
                        continue

                    raw = line[len("data: "):]
                    if raw.strip() == "[DONE]":
                        break

                    chunk = json.loads(raw)
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        full_text += delta
                        await on_token(delta)

    except httpx.TimeoutException:
        if on_error:
            await on_error("llm_timeout")
    except httpx.HTTPError:
        if on_error:
            await on_error("llm_connection_failed")

    return full_text