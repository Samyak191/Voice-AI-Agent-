import json
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from app.session import Session
from app.stt_client import DeepgramSTT
from app.tts_client import DeepgramTTS
from app.llm_client import stream_llm_response
from app.text_buffer import SentenceBuffer
from app.latency import LatencyTracker

FINAL_DEBOUNCE_SECONDS = 0.4
BARGE_IN_CONFIRM_SECONDS = 0.15


async def handle_connection(websocket: WebSocket):
    await websocket.accept()
    session = Session()
    ctx = {
        "stt": None,
        "active_task": None,
        "pending_parts": [],
        "finalize_task": None,
        "ai_speaking": False,
        "barge_in_pending": False,
        "barge_in_confirm_task": None,
    }

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"] is not None:
                if ctx["stt"]:
                    await ctx["stt"].send_audio(message["bytes"])

            elif "text" in message and message["text"] is not None:
                data = json.loads(message["text"])
                await handle_control(websocket, session, data, ctx)

    except WebSocketDisconnect:
        pass
    finally:
        if ctx["stt"]:
            await ctx["stt"].close()
        if ctx["active_task"]:
            ctx["active_task"].cancel()


async def send_error(websocket, code):
    try:
        await websocket.send_json({"type": "error", "code": code})
    except Exception:
        pass


async def cancel_active_turn(ctx, session):
    if ctx["active_task"] and not ctx["active_task"].done():
        ctx["active_task"].cancel()
    ctx["ai_speaking"] = False
    session.new_generation()


async def handle_control(websocket, session, data, ctx):
    msg_type = data.get("type")

    if msg_type == "start_session":
        session.active = True

        async def commit_turn():
            combined = " ".join(ctx["pending_parts"]).strip()
            ctx["pending_parts"] = []
            if len(combined.split()) < 1:
                return

            tracker = LatencyTracker()
            tracker.mark("user_stopped")
            tracker.mark("stt_final")

            await websocket.send_json({"type": "transcript_final", "text": combined})

            await cancel_active_turn(ctx, session)
            ctx["barge_in_pending"] = False

            tracker.mark("llm_request_sent")

            gen = session.generation
            ctx["active_task"] = asyncio.create_task(
                run_turn(websocket, session, combined, gen, tracker, ctx)
            )

        async def schedule_commit():
            if ctx["finalize_task"]:
                ctx["finalize_task"].cancel()

            async def waiter():
                try:
                    await asyncio.sleep(FINAL_DEBOUNCE_SECONDS)
                    await commit_turn()
                except asyncio.CancelledError:
                    pass

            ctx["finalize_task"] = asyncio.create_task(waiter())

        async def on_transcript(text, is_final):
            if not text.strip():
                return

            if ctx["barge_in_pending"] and text.strip():
                if ctx["barge_in_confirm_task"]:
                    ctx["barge_in_confirm_task"].cancel()
                ctx["barge_in_pending"] = False
                await cancel_active_turn(ctx, session)
                await websocket.send_json({"type": "status", "message": "interrupted"})

            if not is_final:
                await websocket.send_json({"type": "transcript_interim", "text": text})
                return

            ctx["pending_parts"].append(text)
            await schedule_commit()

        async def on_speech_started():
            if not ctx["ai_speaking"]:
                return

            ctx["barge_in_pending"] = True

            async def confirm_timeout():
                try:
                    await asyncio.sleep(BARGE_IN_CONFIRM_SECONDS)
                    ctx["barge_in_pending"] = False
                except asyncio.CancelledError:
                    pass

            if ctx["barge_in_confirm_task"]:
                ctx["barge_in_confirm_task"].cancel()
            ctx["barge_in_confirm_task"] = asyncio.create_task(confirm_timeout())

        async def on_stt_error(code):
            await send_error(websocket, code)

        ctx["stt"] = DeepgramSTT(on_transcript, on_stt_error, on_speech_started)
        await ctx["stt"].connect()
        await websocket.send_json({"type": "status", "message": "session_started"})

    elif msg_type == "stop_session":
        session.active = False
        if ctx["stt"]:
            await ctx["stt"].close()
            ctx["stt"] = None
        if ctx["active_task"]:
            ctx["active_task"].cancel()
        await websocket.send_json({"type": "status", "message": "session_stopped"})

    elif msg_type == "barge_in":
        await cancel_active_turn(ctx, session)
        await websocket.send_json({"type": "status", "message": "interrupted"})

    elif msg_type == "mic_error":
        await send_error(websocket, "mic_permission_denied")


async def run_turn(websocket, session, user_text, gen, tracker, ctx):
    session.add_turn("user", user_text)

    def is_current(g):
        return g == session.generation

    first_audio_marked = False

    async def on_tts_error(code):
        await send_error(websocket, code)

    async def send_audio_chunk(chunk, seq):
        nonlocal first_audio_marked
        if not is_current(gen):
            return
        if not first_audio_marked:
            tracker.mark("tts_first_audio")
            first_audio_marked = True
            ctx["ai_speaking"] = True
        try:
            await websocket.send_bytes(chunk)
        except Exception:
            pass

    tts = DeepgramTTS(
        lambda chunk, seq: send_audio_chunk(chunk, seq),
        on_tts_error,
    )
    await tts.connect()

    buffer = SentenceBuffer(
        lambda chunk: handle_sentence_chunk(tts, chunk, gen, is_current)
    )

    full_reply = ""
    first_token_marked = False
    in_think = {"value": False}
    was_cancelled = False

    async def on_token(token):
        nonlocal full_reply, first_token_marked
        if not is_current(gen):
            return

        if not first_token_marked:
            tracker.mark("llm_first_token")
            first_token_marked = True

        text = token
        if "<think>" in text:
            in_think["value"] = True
            text = text.split("<think>")[0]
        if "</think>" in text:
            in_think["value"] = False
            text = text.split("</think>")[-1]

        if in_think["value"]:
            await buffer.add(token)
            return

        full_reply += text
        if text:
            await websocket.send_json({"type": "llm_token", "text": text})
        await buffer.add(token)

    async def on_llm_error(code):
        await send_error(websocket, code)

    try:
        await stream_llm_response(
            session.history, on_token, gen, is_current, on_llm_error
        )

        if is_current(gen):
            await buffer.flush_remaining()
            if full_reply:
                session.add_turn("assistant", full_reply)

    except asyncio.CancelledError:
        was_cancelled = True

    finally:
        if was_cancelled or not is_current(gen):
            await tts.close()
        else:
            tts.mark_no_more_input()
            await tts.wait_until_done()
            await websocket.send_json({
                "type": "latency",
                "data": tracker.snapshot(),
            })
            await tts.close()
        if is_current(gen):
            ctx["ai_speaking"] = False


async def handle_sentence_chunk(tts, chunk, gen, is_current):
    if not is_current(gen):
        return
    await tts.speak(chunk)