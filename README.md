# Voice AI Assistant

A real-time, streaming voice AI assistant. The user speaks, sees a live transcript, watches the AI's response stream in as text, and hears it spoken back — all with sub-pipeline components streaming concurrently rather than waiting on each other.

## Stack

- **Backend:** FastAPI (Python), async/await throughout
- **STT:** Deepgram (`nova-3`, streaming WebSocket, VAD-enabled)
- **LLM:** Groq (`qwen/qwen3.6-27b`, HTTP streaming)
- **TTS:** Deepgram (`aura-2-asteria-en`, streaming WebSocket)
- **Frontend:** React (Vite), Web Audio API, native WebSocket

## Setup

**Backend**
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
Create `backend/.env`:

DEEPGRAM_API_KEY=your_key_here
GROQ_API_KEY=your_key_here

Run:
```powershell
uvicorn app.main:app --reload --port 8000
```

**Frontend**
```powershell
cd frontend
npm install
```
Create `frontend/.env`:

VITE_WS_URL=ws://localhost:8000/ws

Run:
```powershell
npm run dev
```

## Architecture

Browser (mic)
| WebSocket
v
FastAPI backend (session + generation id)
| | |
v v v
STT LLM TTS
Deepgram Groq Deepgram
nova-3 (HTTP SSE) aura-2
| | |
v v v
Audio + text stream
|
v
Browser (playback)


Three separate connections carry the pipeline:

1. **Browser ↔ Backend** — one persistent WebSocket. Carries raw mic audio upstream; carries interim/final transcripts, streaming LLM tokens, audio chunks, latency data, and errors downstream. Chosen because this leg needs continuous, low-latency, bidirectional exchange — exactly what WebSockets are for.
2. **Backend ↔ Deepgram STT** — WebSocket. Audio streams in, transcripts stream out, on the same connection, in real time.
3. **Backend ↔ Deepgram TTS** — WebSocket. Text goes in, audio bytes come out, same connection.

**The one exception: Backend ↔ Groq (LLM) is plain HTTP streaming (SSE-style), not a WebSocket.** This is deliberate, not an oversight. The LLM leg only needs one-directional streaming — the backend sends one request, the model streams tokens back on the same open HTTP response. There's no need for the client to send anything mid-stream, so a WebSocket's bidirectional channel would be unused overhead. REST/HTTP streaming is the natural fit for a "request once, stream the answer" pattern; WebSockets earn their cost only when both sides need to talk continuously, which is true for the audio legs but not the LLM leg.

**Where Redis / a queue / a database would fit, if this were scaled beyond a single-process demo:**
- **Redis** would hold session state (`generation`, `pending_parts`, conversation history) instead of the current in-memory Python dict, so any backend replica could pick up a reconnecting client rather than requiring session affinity.
- **A queue** (e.g. RabbitMQ, or Redis Streams) would sit between STT-finalization and LLM-dispatch if you needed to handle bursts of concurrent users beyond what direct async task creation can absorb, or to persist/retry failed generations.
- **A database** would store completed conversation transcripts for analytics or continuity across sessions (right now, history lives only in memory for the life of the WebSocket connection and is lost on disconnect).

For a single-user technical assessment, none of these were necessary — the in-memory `asyncio` primitives (queues, events, tasks) do the same job at this scale with far less operational overhead, which is the right trade-off for the deployment size being tested here.

## Latency

Measured, not assumed. Real example from testing:

| Stage | Duration |
|---|---|
| STT finalize | ~0ms |
| Debounce (merges multi-part sentences) | ~400ms |
| LLM to first token | ~1100ms |
| TTS to first audio | ~719ms |
| **Total to first audio** | **~2200ms** |

The dominant cost is the LLM's own generation time on Groq — this is largely outside our control beyond model selection. Ideas for further reduction, each a real trade-off:
- **Smaller LLM** (e.g. a lighter model than the current 27B) for faster first-token, at some cost to answer quality/coherence.
- **Shorter TTS flush boundary** — currently we wait for a full sentence before sending text to TTS; flushing at a clause/comma boundary instead would start audio sooner at a small cost to prosody.
- **Pre-warm the TTS WebSocket** before the LLM finishes, rather than opening it fresh per turn.
- **Shrink the debounce window further** — already tuned down from 700ms to 400ms; further reduction risks re-splitting a user's own natural mid-sentence pause into two turns (a real bug we hit and fixed during development).

## Why not send every LLM token directly to TTS?

Per-token TTS requests would mean firing a network call for every few characters — dozens of tiny HTTP/WebSocket messages per response, each with its own overhead, plus broken prosody (TTS engines need a reasonably complete phrase to produce natural intonation) and a real risk of hitting rate limits. Instead, tokens accumulate in a buffer until a sentence boundary (`.`, `!`, `?`, or a max-length safety cap) is hit, and only then is that chunk sent to TTS — giving the model a complete phrase to work with while still starting audio well before the full response is generated.

## Conversation history

- Stored in-memory per WebSocket connection, as a list of `{role, content}` messages, with a pinned system prompt always at index 0.
- Sent to the LLM as the `messages` array on every request — full history each time (the model has no memory between calls).
- **Growth handling:** trimmed to the last 19 turns plus the system prompt whenever it exceeds 20 entries, so the array never grows unbounded. In a production system with persistent history, this would instead move to a summarization strategy (periodically collapsing older turns into a short summary) or a sliding window backed by a database, so history could survive beyond a single connection's lifetime.

## The three logical challenges

**Ghost Audio (interruption produces stale audio)**
Every new user turn increments `session.generation`. Every async callback in the pipeline (`on_token`, TTS chunk dispatch, audio-send) checks `is_current(generation)` before doing anything. A cancelled generation's callbacks become silent no-ops even if they were already mid-flight when cancellation happened. The frontend mirrors this: a new generation forcibly stops any already-scheduled audio sources (`AudioContext` `.stop()` on all active buffer sources), so stale audio can never play even if a stale callback somehow slipped through.

**Slow component (TTS suddenly takes 3s)**
LLM token streaming and TTS dispatch are decoupled by an `asyncio.Queue`. A single background worker pulls sentences off the queue and sends them to TTS one at a time; a slow or stuck TTS call does not block the LLM's token stream from continuing to reach the UI, nor does it block the next sentence from being queued. Each TTS network call has its own timeout, so a truly stuck request degrades gracefully (an error is surfaced) instead of hanging the whole turn indefinitely. This was validated with a `SIMULATE_SLOW_TTS` flag that randomly injects a 3-second delay into TTS calls.

**Duplicate audio chunks**
Every TTS audio chunk carries a sequence number. The frontend's audio scheduler only plays a chunk once its sequence number matches the next expected one, buffering out-of-order arrivals until their turn comes, and silently dropping any chunk whose sequence number has already been played or is already queued — preventing both re-ordering artifacts and audible duplication. Validated with a `SIMULATE_DUPLICATE_CHUNKS` flag that deliberately re-sends every 4th chunk.

## Interruption / barge-in

Real voice-activity detection (Deepgram's `SpeechStarted` event), not word-count heuristics. Barge-in only arms once the AI has actually started producing audible output (not during the "thinking" gap before first token), preventing the user's own natural speech from self-interrupting a response that hasn't started yet. A short confirmation window filters out single-blip false positives (stray noise, breath) while still reacting within a few hundred milliseconds of genuine speech.

## Error handling

Explicit handling for: STT connection failure, TTS connection/request failure, LLM timeout/bad response, WebSocket disconnection, microphone permission denial, and empty transcripts. Failures surface as a visible error message in the UI rather than freezing silently.

## Known limitations

- Acoustic feedback (AI's own voice re-entering the mic) can cause false barge-in on speaker playback; mitigated with browser echo cancellation and a confirmation window, but headphones give the cleanest experience — a known trade-off of browser-based `AudioContext` playback versus a dedicated AEC-tuned audio pipeline.
- Conversation history is in-memory only and does not survive a disconnect/reconnect.
- Total latency (~2s to first audio) exceeds the assignment's illustrative example (~950ms); the gap is measured and understood (see Latency section above) rather than unaccounted for.


