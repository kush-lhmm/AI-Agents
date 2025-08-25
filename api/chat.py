from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import os
from .prompt_loader import render_system_content
from datetime import date

load_dotenv()

router = APIRouter()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is not set")

client = OpenAI(api_key=api_key)

class ChatRequest(BaseModel):
    message: str
    model: str = "gpt-4.1-nano" 

class ChatIn(BaseModel):
    message: str

@router.post("/chat")
def chat(body: ChatIn):
    system_text = render_system_content({
        "brand": "Diffrun",
        "today": date.today().isoformat(),
    })

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": system_text},
                {"role": "user", "content": body.message},
            ],
            temperature=0.2,
        )
        return {"reply": resp.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))