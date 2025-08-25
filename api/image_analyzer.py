from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional, Any, Dict
from pydantic import ValidationError
import base64, os, json, pathlib

from openai import OpenAI
from models.person_analysis import PersonImageAnalysis
from utils.json_schema_patch import forbid_additional_properties

router = APIRouter(prefix="/image", tags=["image"])

# ---- Config ----
SCHEMA_PATH = pathlib.Path("schema/person.json")
ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
MAX_BYTES = 6 * 1024 * 1024

def _load_and_prepare_schema() -> Dict[str, Any]:
    """
    Load the exported schema/person.json and ensure it matches OpenAI's structured outputs requirements:
    - Wrapper: { "name": ..., "schema": {...}, "strict": true }
    - For every object: additionalProperties must be present and be false.
    """
    if not SCHEMA_PATH.exists():
        raise RuntimeError(f"Schema file not found at {SCHEMA_PATH}")

    raw = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    # Support two common shapes:
    # 1) Already wrapped: {"name": "...", "schema": {...}, "strict": true}
    # 2) Bare JSON Schema object (root is the schema)
    if isinstance(raw, dict) and "schema" in raw and "name" in raw:
        schema_core = raw["schema"]
        name = raw["name"]
    else:
        # If user saved only the core JSON Schema (from model_json_schema), wrap it
        schema_core = raw
        name = "person_image_analysis"

    # Patch to add additionalProperties:false everywhere it's an object
    patched_core = forbid_additional_properties(schema_core)

    return {"name": name, "schema": patched_core, "strict": True}

# Load & patch once at import time (fail fast if broken)
PERSON_JSON_SCHEMA = _load_and_prepare_schema()

def to_data_url(content: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(content).decode('utf-8')}"

def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)

@router.post("/analyze", response_model=PersonImageAnalysis)
async def analyze_image(image: UploadFile = File(...), goal: Optional[str] = Form("")):
    # ---- request validation ----
    if image.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {image.content_type or 'unknown'}")
    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 6MB)")

    data_url = to_data_url(content, image.content_type)

    # ---- prompts ----
    system_prompt = (
        "You are a vision analyst. Return ONLY valid JSON per the json_schema.\n"
        "- First detect if any people/faces are present.\n"
        "- For each detected face, fill attributes strictly using the provided enums.\n"
        "- Use 'unclear' when uncertain. Never guess identity, name, or sensitive attributes "
        "(e.g., race, ethnicity, nationality, religion, political views, disabilities).\n"
        "- Age must be coarse (child/teen/adult/senior) and may be 'unclear'.\n"
        "- BBox values are normalized floats in [0,1].\n"
        "- Suggested actions should be pragmatic (e.g., retake photo, adjust lighting), "
        "and if a goal is provided, tailor them to that goal without making medical or legal claims."
    )

    user_text = (
        "Analyze this image. If text is present, OCR it into 'ocr_text'. "
        "Infer environment (setting + up to 5 dominant colors). "
        "If no person is present, set has_person=false, num_faces=0, faces=[]. "
        "If person(s) present, enumerate faces with hair(style/length/color), eyes(color/eyewear), "
        "facial hair, headwear, expression, pose, accessories, and a normalized bbox. "
        "Fill safety flags (nsfw, minors_possible, sensitive_context). "
        "Provide 2–4 actionable 'suggested_actions'."
    )
    if goal and goal.strip():
        user_text += f" The user's goal is: '{goal.strip()}'. Tailor 'suggested_actions' accordingly."

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
            response_format={
                "type": "json_schema",
                "json_schema": PERSON_JSON_SCHEMA,  # <- patched & wrapped
            },
            temperature=0.1,
        )

        raw = resp.choices[0].message.content
        parsed = PersonImageAnalysis.model_validate_json(raw)
        return parsed

    except ValidationError as ve:
        # Pydantic validation failed: schema mismatch from the model output
        raise HTTPException(status_code=502, detail=f"Schema validation failed: {ve}")
    except Exception as e:
        # Upstream or other errors
        raise HTTPException(status_code=500, detail=f"Image analysis failed: {str(e)}")
