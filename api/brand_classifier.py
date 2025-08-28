from fastapi import APIRouter, UploadFile, File, HTTPException
import base64, os
from openai import OpenAI

router = APIRouter(prefix="/brand", tags=["brand"])

ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
MAX_BYTES = 6 * 1024 * 1024  # 6 MB

def to_data_url(content: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(content).decode('utf-8')}"

def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)

@router.post("/classify")
async def classify_brand(image: UploadFile = File(...)):
    # --- validation ---
    if image.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {image.content_type or 'unknown'}")
    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 6MB)")

    data_url = to_data_url(content, image.content_type)

    # --- prompts (strict) ---
    system_prompt = (
        "You are a vision classifier. Decide which tobacco brand the image most likely shows. "
        "Allowed outputs ONLY: 'marlboro', 'classic', 'goldflake', 'i don't know'. "
        "If uncertain, output exactly 'i don't know'. "
        "Respond with a single JSON object: {\"label\": \"<one of the allowed strings>\"}. "
        "No explanations. No extra fields."
    )
    user_prompt = (
        "Classify the image into one of: marlboro, classic, goldflake; else 'i don't know'."
    )

    model_name = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")

    try:
        client = get_openai_client()
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                {"role": "user", "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]},
            ],
            # Keep it simple: plain JSON object, we’ll trust the strict instruction
            temperature=0.0,
        )
        raw = resp.choices[0].message.content or ""
        # Expecting something like: {"label":"marlboro"}
        # Return as-is to keep response minimal.
        # Optional: you can parse & validate here; keeping minimal per your ask.
        return {"result": raw}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Brand classification failed: {str(e)}")
