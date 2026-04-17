import os
import logging
from dotenv import load_dotenv

load_dotenv()  # Must run before any other imports that use env vars

from fastapi import FastAPI, Request, Response
import pipeline
import debounce
from whatsapp import send_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()
# Add your team's own WhatsApp numbers here to prevent the bot from replying to itself
OWN_PHONE_IDS: set[str] = set()


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
        if reply:
            result = await send_message(wa_id, reply)
            logger.info(f"Sent reply to {wa_id}: {result}")
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

        wa_id = message["from"]

        # Skip messages from own number to avoid echo loops
        if wa_id in OWN_PHONE_IDS:
            logger.info(f"Skipping message from own number: {wa_id}")
            return {"status": "ok"}

        text = message["text"]["body"]
        logger.info(f"Message from {wa_id}: {text}")

        # Buffer message — fires callback after 10s of silence
        await debounce.add_message(wa_id, text, process_and_send)

    except Exception as e:
        logger.error(f"Error handling webhook: {e}", exc_info=True)

    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
