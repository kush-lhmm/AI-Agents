import os
import httpx

WA_PHONE_ID = os.getenv("WA_PHONE_ID", "")
WA_TOKEN = os.getenv("WA_TOKEN", "")

class WhatsAppClient:
    def __init__(self):
        if not WA_PHONE_ID or not WA_TOKEN:
            raise RuntimeError("Missing WA_PHONE_ID or WA_TOKEN in environment.")
        self._url = f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages"
        self._headers = {
            "Authorization": f"Bearer {WA_TOKEN}",
            "Content-Type": "application/json",
        }

    async def send_text(self, to: str, body: str):
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(self._url, headers=self._headers, json=payload)
            r.raise_for_status()
            return r.json()

wa_client = WhatsAppClient()
