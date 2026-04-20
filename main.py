import os
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()  # Must run before any other imports that use env vars

from fastapi import FastAPI, Request, Response
import pipeline
import debounce
import state as st
from whatsapp import send_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()
OWNER_NUMBER = "919265335430"
OWN_PHONE_IDS: set[str] = set()

# Deduplicate Meta webhook retries — store seen message IDs (bounded to last 10k)
_seen_message_ids: set[str] = set()


@app.get("/webhook")
async def verify_webhook(request: Request):
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("Webhook verification failed")
    return Response(status_code=403)


async def process_and_send(wa_id: str, combined_text: str):
    try:
        reply = await pipeline.process_message(wa_id, combined_text)
        if not reply:
            return
        messages = [reply] if isinstance(reply, str) else reply
        for msg in messages:
            if msg:
                result = await send_message(wa_id, msg)
                logger.info(f"Sent reply to {wa_id}: {result}")
                if len(messages) > 1:
                    await asyncio.sleep(1.5)
    except Exception as e:
        logger.error(f"Pipeline error for {wa_id}: {e}", exc_info=True)


@app.post("/webhook")
async def handle_webhook(request: Request):
    body = await request.json()
    logger.info(f"Incoming webhook: {body}")

    try:
        entry = body.get("entry", [{}])[0]
        change = entry.get("changes", [{}])[0]
        value = change.get("value", {})

        if "messages" not in value:
            return {"status": "ok"}

        message = value["messages"][0]

        if message.get("type") != "text":
            logger.info(f"Skipping non-text message type: {message.get('type')}")
            return {"status": "ok"}

        msg_id = message.get("id", "")
        if msg_id and msg_id in _seen_message_ids:
            logger.info(f"Duplicate message ID {msg_id} — skipping")
            return {"status": "ok"}
        if msg_id:
            _seen_message_ids.add(msg_id)
            if len(_seen_message_ids) > 10000:
                _seen_message_ids.clear()

        wa_id = message["from"]
        text = message["text"]["body"]
        logger.info(f"Message from {wa_id}: {text}")

        # Skip messages from own number to avoid echo loops
        if wa_id in OWN_PHONE_IDS:
            logger.info(f"Skipping message from own number: {wa_id}")
            return {"status": "ok"}

        # Owner commands
        if wa_id == OWNER_NUMBER:
            stripped = text.strip()
            cmd = stripped.upper()
            if cmd.startswith("STOP "):
                target = stripped[5:].strip().replace("+", "").replace(" ", "")
                st.mark_owner_takeover(target)
                await send_message(OWNER_NUMBER, f"✅ Bot stopped for +{target}. You have full control.")
                logger.info(f"Owner takeover for {target}")
            elif cmd == "RESET ALL":
                st.reset_all()
                await send_message(OWNER_NUMBER, "✅ All conversations reset.")
                logger.info("All conversations reset by owner")
            elif cmd.startswith("RESET "):
                target = stripped[6:].strip().replace("+", "").replace(" ", "")
                st.reset_conversation(target)
                await send_message(OWNER_NUMBER, f"✅ Conversation reset for +{target}. Bot will treat them as new.")
                logger.info(f"Conversation reset for {target}")
            return {"status": "ok"}

        # Buffer message — fires callback after 10s of silence
        await debounce.add_message(wa_id, text, process_and_send)

    except Exception as e:
        logger.error(f"Error handling webhook: {e}", exc_info=True)

    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
