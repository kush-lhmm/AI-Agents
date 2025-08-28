# api/vision_combo.py
from fastapi import APIRouter, UploadFile, File, HTTPException
import base64, os, json
from openai import OpenAI

router = APIRouter(prefix="/vision", tags=["vision"])

ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
MAX_BYTES = 6 * 1024 * 1024  # 6 MB

def to_data_url(content: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(content).decode('utf-8')}"

def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)

# ---- Strict schemas (keep them tiny) ----
QR_SCHEMA = {
    "name": "qr_detection",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"qr": {"type": "boolean"}},
        "required": ["qr"],
    },
}

BRAND_SCHEMA = {
    "name": "brand_classification",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "label": {
                "type": "string",
                "enum": ["marlboro", "classic", "goldflake", "i don't know"]
            }
        },
        "required": ["label"],
    },
}

def _openai():
    model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
    return get_openai_client(), model

def _qr_detect(data_url: str) -> bool:
    client, model = _openai()
    sys = (
        "You are a vision model. Return STRICT JSON only per json_schema. "
        "Task: detect whether any QR code is present in the image."
    )
    user = "Answer with {\"qr\": true} if a QR code is present, else {\"qr\": false}."
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": [{"type": "text", "text": sys}]},
            {"role": "user", "content": [
                {"type": "text", "text": user},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]},
        ],
        response_format={"type": "json_schema", "json_schema": QR_SCHEMA},
        temperature=0,
    )
    payload = json.loads(resp.choices[0].message.content or "{}")
    return bool(payload.get("qr", False))

def _brand_classify(data_url: str) -> str:
    client, model = _openai()
    sys = (
        "You are a vision classifier. Return STRICT JSON only per json_schema. "
        "Classify into exactly one of: 'marlboro', 'classic', 'goldflake', or 'i don't know' if uncertain."
    )
    # Keep brand task isolated (was accurate before) — no mention of QR here.
    user = "Classify the brand visible in the image."
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": [{"type": "text", "text": sys}]},
            {"role": "user", "content": [
                {"type": "text", "text": user},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]},
        ],
        response_format={"type": "json_schema", "json_schema": BRAND_SCHEMA},
        temperature=0,
    )
    payload = json.loads(resp.choices[0].message.content or "{}")
    label = payload.get("label")
    if label not in {"marlboro", "classic", "goldflake", "i don't know"}:
        label = "i don't know"
    return label

@router.post("/analyze")
async def analyze_qr_and_brand(image: UploadFile = File(...)):
    # ---- validation ----
    if image.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {image.content_type or 'unknown'}")
    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 6MB)")

    data_url = to_data_url(content, image.content_type)

    try:
        # Run as two small, independent tasks for reliability
        qr = _qr_detect(data_url)
        brand = _brand_classify(data_url)
        return {"qr": qr, "brand": brand}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vision analysis failed: {str(e)}")
