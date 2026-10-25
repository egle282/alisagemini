import asyncio
import json
import logging
from typing import Any, Dict, List
from collections import defaultdict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from aliceio import Dispatcher, Skill
from aliceio.types import Message, Response

from config import settings
from gemini_client import gemini_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("alice_gemini_skill")

app = FastAPI(title="Alice Gemini Skill", version="1.0.0")

dp = Dispatcher()
skill = Skill(skill_id="alice-gemini-skill")

# In-memory session history: user_id -> list of {'role': str, 'text': str} (max 3 pairs)
user_dialog_history: Dict[str, List[dict]] = defaultdict(list)


@dp.message()
async def handle_message(message: Message) -> Response:
    """Handle incoming message from Alice."""
    # Check if this is a new session
    is_new = bool(message.session.new if message.session else False)
    if is_new:
        return Response(text=settings.welcome_message, end_session=False)

    user_text = message.command or message.original_utterance or ""
    user_id = message.session.user_id if message.session else "anonymous"

    if not user_text.strip():
        return Response(text=settings.empty_query_message, end_session=False)

    history = user_dialog_history[user_id]
    reply_text = await gemini_client.generate_response(user_text=user_text, history=history)

    # Store last 3 interactions
    history.append({"role": "user", "text": user_text})
    history.append({"role": "model", "text": reply_text})
    user_dialog_history[user_id] = history[-6:]

    return Response(text=reply_text, end_session=False)


@app.get("/")
async def root():
    return {"status": "ok", "service": "Alice Gemini Skill"}


@app.get("/ping")
async def ping():
    return {"status": "pong"}


@app.post("/webhook")
async def webhook_endpoint(request: Request):
    """
    Main webhook endpoint for Yandex.Dialogs.
    Validates Alice JSON, feeds update to aliceio Dispatcher, and guarantees fast response.
    """
    try:
        body = await request.json()
    except Exception as e:
        logger.error("Failed to parse request JSON: %s", str(e))
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON format"},
        )

    # Handle Alice ping checks
    if body.get("request", {}).get("command") == "ping":
        return JSONResponse(
            content={
                "response": {"text": "pong", "end_session": False},
                "version": body.get("version", "1.0"),
            }
        )

    try:
        # Feed webhook update to aliceio dispatcher with overall 2.9s safety timeout
        alice_response = await asyncio.wait_for(
            dp.feed_webhook_update(skill, body),
            timeout=2.9,
        )

        if alice_response:
            return JSONResponse(content=alice_response.model_dump(exclude_none=True))

        # Fallback if no handler produced response
        return JSONResponse(
            content={
                "response": {"text": settings.empty_query_message, "end_session": False},
                "version": body.get("version", "1.0"),
            }
        )
    except asyncio.TimeoutError:
        logger.warning("Webhook dispatch exceeded 2.9s safety timeout")
        return JSONResponse(
            content={
                "response": {
                    "text": settings.timeout_fallback_message,
                    "end_session": False,
                },
                "version": body.get("version", "1.0"),
            }
        )
    except Exception as e:
        logger.exception("Error processing webhook update: %s", str(e))
        return JSONResponse(
            content={
                "response": {
                    "text": settings.api_error_fallback_message,
                    "end_session": False,
                },
                "version": body.get("version", "1.0"),
            }
        )


def handler(event: Any, context: Any) -> Any:
    """
    Entrypoint for Yandex Cloud Functions (Python 3.12).
    Processes event from Yandex.Dialogs directly.
    """
    if event is None:
        event = {}

    is_direct_alice = isinstance(event, dict) and "request" in event and "session" in event

    try:
        if is_direct_alice:
            body = event
        else:
            http_method = event.get("httpMethod", "POST") if isinstance(event, dict) else "POST"
            if http_method == "GET":
                return {
                    "statusCode": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"status": "ok", "service": "Alice Gemini Skill"}),
                }

            body_raw = event.get("body", "{}") if isinstance(event, dict) else "{}"
            if isinstance(event, dict) and event.get("isBase64Encoded", False):
                import base64
                body_raw = base64.b64decode(body_raw).decode("utf-8")

            body = json.loads(body_raw) if isinstance(body_raw, str) else body_raw
            if not isinstance(body, dict):
                body = {}

        # If body is empty or not a valid Alice structure, return default greeting
        if not body or not isinstance(body, dict) or "meta" not in body or "request" not in body:
            default_resp = {
                "response": {"text": settings.welcome_message, "end_session": False},
                "version": "1.0",
            }
            if is_direct_alice:
                return default_resp
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(default_resp, ensure_ascii=False),
            }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            alice_response = loop.run_until_complete(
                asyncio.wait_for(dp.feed_webhook_update(skill, body), timeout=3.5)
            )
            resp_dict = (
                alice_response.model_dump(exclude_none=True)
                if alice_response
                else {
                    "response": {"text": settings.welcome_message, "end_session": False},
                    "version": body.get("version", "1.0") if isinstance(body, dict) else "1.0",
                }
            )
        finally:
            loop.close()

        # If invoked directly by Alice (raw payload without httpMethod wrapper)
        if is_direct_alice:
            return resp_dict

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(resp_dict, ensure_ascii=False),
        }
    except asyncio.TimeoutError:
        fallback = {
            "response": {
                "text": settings.timeout_fallback_message,
                "end_session": False,
            },
            "version": "1.0",
        }
        if is_direct_alice:
            return fallback
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(fallback, ensure_ascii=False),
        }
    except Exception as e:
        logger.exception("Error in Cloud Functions handler: %s", str(e))
        err_msg = f"Ошибка: {type(e).__name__}: {str(e)[:200]}"
        err_fallback = {
            "response": {
                "text": err_msg,
                "end_session": False,
            },
            "version": "1.0",
        }
        if is_direct_alice:
            return err_fallback
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(err_fallback, ensure_ascii=False),
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
