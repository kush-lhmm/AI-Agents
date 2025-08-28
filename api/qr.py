from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
import base64, os

from openai import OpenAI

router = APIRouter(prefix="/qr", tags=["qr"])

# ---- Config ----
ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
MAX_BYTES = 6 * 1024 * 1024

def to_data_url(content: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(content).decode('utf-8')}"

def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)

@router.post("/scan")
async def scan_qr(image: UploadFile = File(...)):
    # ---- request validation ----
    if image.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {image.content_type or 'unknown'}")
    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 6MB)")

    data_url = to_data_url(content, image.content_type)

    # ---- prompt ----
    system_prompt = (
        "You are a vision model. Look at the image and ONLY answer whether a QR code is present."
        " Respond strictly as JSON with: {\"qr\": true/false, \"message\": \"QR code detected\" or \"QR code not found\"}."
    )

    user_text = "Check if this image contains a QR code."

    model_name = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")

    try:
        client = get_openai_client()
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]},
            ],
            temperature=0,
        )

        raw = resp.choices[0].message.content
        return {"result": raw}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QR scan failed: {str(e)}")
