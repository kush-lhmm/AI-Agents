import os
import httpx

BACKEND_BASE = os.getenv("BACKEND_BASE", "http://127.0.0.1:8000")

async def tata_reply(user_text: str) -> str:
    """Call your Tata chat endpoint and return the reply string."""
    payload = {"message": user_text}  # /api/tata/chat only needs 'message'
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BACKEND_BASE}/api/tata/chat", json=payload)
        r.raise_for_status()
        data = r.json()
        # ChatOut has 'reply', 'used_results', 'meta'
        return (data.get("reply") or "").strip() or "Sorry, I don't have enough information."