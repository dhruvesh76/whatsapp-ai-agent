import os
import httpx

PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
API_URL = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"


async def send_message(to: str, text: str) -> dict:
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(API_URL, json=payload, headers=headers)
        return resp.json()
