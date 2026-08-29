import os
from dotenv import load_dotenv

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

DEEPGRAM_STT_MODEL = "nova-3"
DEEPGRAM_TTS_MODEL = "aura-2-asteria-en"
GROQ_LLM_MODEL = "qwen/qwen3.6-27b"

SIMULATE_SLOW_TTS = os.getenv("SIMULATE_SLOW_TTS", "false").lower() == "true"
SLOW_TTS_DELAY_SECONDS = 3
SIMULATE_DUPLICATE_CHUNKS = os.getenv("SIMULATE_DUPLICATE_CHUNKS", "false").lower() == "true"