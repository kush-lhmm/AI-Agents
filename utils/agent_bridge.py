import os
import httpx

BACKEND_BASE = os.getenv("BACKEND_BASE", "http://127.0.0.1:8000")

async def vision_analyze_file(content: bytes, content_type: str) -> dict:
    """
    Send image bytes to /api/vision/analyze (multipart) and return JSON:
    { "qr": bool, "brand": "marlboro|classic|goldflake|i don't know" }
    """
    files = {"image": ("photo", content, content_type or "application/octet-stream")}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{BACKEND_BASE}/api/vision/analyze", files=files)
        r.raise_for_status()
        return r.json()

# Optional: keep a text fallback so old imports don't break
async def vision_reply(user_text: str) -> str:
    return "Send a clear storefront photo to analyze QR presence and brand."

# Optional: keep tata_reply as alias
async def tata_reply(user_text: str) -> str:
    return await vision_reply(user_text)
