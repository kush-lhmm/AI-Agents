import os
import re
import json
import hmac
import hashlib
import httpx

WA_PHONE_ID = os.getenv("WA_PHONE_ID", "")
WA_TOKEN = os.getenv("WA_TOKEN", "")
WA_APP_SECRET = os.getenv("WA_APP_SECRET", "")  # optional but recommended

class WhatsAppClient:
    def __init__(self):
        if not WA_PHONE_ID or not WA_TOKEN:
            raise RuntimeError("Missing WA_PHONE_ID or WA_TOKEN in environment.")
        self._url = f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages"
        self._headers = {
            "Authorization": f"Bearer {WA_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        # Precompute appsecret_proof if we have the app secret
        self._params = {}
        if WA_APP_SECRET:
            self._params["appsecret_proof"] = hmac.new(
                WA_APP_SECRET.encode(), msg=WA_TOKEN.encode(), digestmod=hashlib.sha256
            ).hexdigest()

    @staticmethod
    def _normalize_to(to: str) -> str:
        # Keep digits only; require 8–15 digits (typical E.164 length range)
        n = re.sub(r"\D", "", to or "")
        if not re.fullmatch(r"\d{8,15}", n):
            raise ValueError(f"Invalid 'to' number (needs E.164 digits only), got: {to!r}")
        return n

    async def _post(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(self._url, headers=self._headers, params=self._params, json=payload)
            if r.status_code >= 400:
                # Surface exact error payload to logs/caller
                try:
                    err = r.json()
                except Exception:
                    err = {"raw": r.text}
                # Common patterns: code 100 (payload), 131000 (params), 470 (>24h session)
                raise RuntimeError(f"/messages {r.status_code}: {json.dumps(err, ensure_ascii=False)}")
            return r.json()

    async def send_text(self, to: str, body: str, preview_url: bool = False) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": self._normalize_to(to),
            "type": "text",
            "text": {"body": body, "preview_url": preview_url},
        }
        return await self._post(payload)

    async def send_template(self, to: str, template_name: str, lang_code: str = "en_US", components: list | None = None) -> dict:
        # Use if you hit code 470 (outside 24h window)
        payload = {
            "messaging_product": "whatsapp",
            "to": self._normalize_to(to),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": lang_code},
                "components": components or [],
            },
        }
        return await self._post(payload)

wa_client = WhatsAppClient()
