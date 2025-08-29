import os
import httpx

BACKEND_BASE = os.getenv("BACKEND_BASE", "http://127.0.0.1:8000")

async def vision_reply(user_text: str) -> str:
    """
    Call your Vision Combo endpoint and return a plain-text reply.

    Expected response fields (flexible): 'reply' | 'answer' | 'result' | 'message'.
    """
    payload = {"message": user_text}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{BACKEND_BASE}/api/vision/analyze", json=payload)
        r.raise_for_status()
        data = r.json()

    reply = (
        (data.get("reply")
         or data.get("answer")
         or data.get("result")
         or data.get("message")
         or "")
        .strip()
    )
    return reply or "Sorry, I couldn't generate a response."

# Optional: keep tata_reply as a pass-through to avoid breaking other imports elsewhere
async def tata_reply(user_text: str) -> str:
    return await vision_reply(user_text)
