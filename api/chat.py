from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from datetime import date
from pathlib import Path
import json
import os

load_dotenv()

router = APIRouter()

# --- OpenAI client ---
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is not set")

client = OpenAI(api_key=api_key)
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")

# --- Load system prompt JSON once at import ---
# /api/chat.py  -> project root assumed to be parent of "api"  -> /prompts/nutrition_system.json
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = PROJECT_ROOT / "prompts" / "nutrition_system.json"

if not PROMPT_PATH.is_file():
    raise RuntimeError(f"System prompt file not found: {PROMPT_PATH}")

try:
    with PROMPT_PATH.open("r", encoding="utf-8") as f:
        _prompt_json = json.load(f)
except json.JSONDecodeError as e:
    raise RuntimeError(f"Invalid JSON in {PROMPT_PATH}: {e}")

# Expect the JSON to have a single string field "system"
if not isinstance(_prompt_json, dict) or "system" not in _prompt_json or not isinstance(_prompt_json["system"], str):
    raise RuntimeError(f"{PROMPT_PATH} must contain a string field 'system'")

_SYSTEM_TEMPLATE = _prompt_json["system"]
# The template can use {brand} and {today}, e.g. "You are {brand}'s nutrition bot. Today is {today}."

def render_system_text(*, brand: str, today_str: str) -> str:
    """
    Fast, safe formatter. If a placeholder is missing in the template, str.format will raise a KeyError.
    We trap and rethrow a clear error so you know to fix the JSON.
    """
    try:
        return _SYSTEM_TEMPLATE.format(brand=brand, today=today_str)
    except KeyError as e:
        raise RuntimeError(f"Missing placeholder in system template: {e}. "
                           f"Ensure your JSON uses {{brand}} and/or {{today}} as needed.")

# --- Request models ---
class ChatIn(BaseModel):
    message: str
    model: str | None = None  # allow override

# --- Route ---
@router.post("/chat")
def chat(body: ChatIn):
    system_text = render_system_text(
        brand="Diffrun",
        today_str=date.today().isoformat(),
    )

    try:
        resp = client.chat.completions.create(
            model=body.model or DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": body.message},
            ],
            temperature=0.2,
        )
        return {"reply": resp.choices[0].message.content}
    except Exception as e:
        # Bubble up a clean 500 with the underlying error message
        raise HTTPException(status_code=500, detail=str(e))