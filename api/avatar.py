import os, uuid, base64
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_OK = True
except Exception:
    HEIC_OK = False

from openai import OpenAI

router = APIRouter(tags=["avatar"])

ALLOWED_CT = {"image/png", "image/jpeg", "image/webp"}
MEDIA_DIR = os.path.join(os.path.dirname(__file__), "..", "media")
AVATAR_DIR = os.path.join(MEDIA_DIR, "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)

client = OpenAI()  

def _as_data_url_png(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")

@router.post("/avatar")
async def create_avatar(request: Request, prompt: str = Form(...), image: UploadFile = File(...)):
    if image.content_type not in ALLOWED_CT:
        raise HTTPException(415, f"Unsupported type: {image.content_type}")

    raw = await image.read()
    data_url = _as_data_url_png(raw)

    try:
        resp = client.responses.create(
            model="gpt-4.1",
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url},
                ],
            }],
            tools=[{"type": "image_generation"}],  
        )
    except Exception as e:
        raise HTTPException(502, f"OpenAI error: {e}")

    # Extract first generated image (base64)
    images_b64 = [
        o.result for o in (resp.output or [])
        if getattr(o, "type", "") == "image_generation_call"
    ]
    if not images_b64:
        raise HTTPException(500, "No image returned by model.")

    out_bytes = base64.b64decode(images_b64[0])
    file_id = f"{uuid.uuid4().hex}.png"
    out_path = os.path.abspath(os.path.join(AVATAR_DIR, file_id))
    with open(out_path, "wb") as f:
        f.write(out_bytes)

    # Absolute URL for UI
    base = str(request.base_url).rstrip("/")
    url = f"{base}/media/avatars/{file_id}"

    return JSONResponse({"url": url, "format": "png", "aspect_ratio": "1:1"})
