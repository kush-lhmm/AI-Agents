import os
import urllib.parse
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager
import httpx
from dotenv import load_dotenv
import hmac, hashlib
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from utils.gmail_chat_agent import chat_agent
from utils.ingest import ingest

@asynccontextmanager
async def lifespan(app: FastAPI):
    required = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars for agent: {', '.join(missing)}")
    chat_agent.start()
    try:
        yield
    finally:
        try:
            await chat_agent.stop()
        except Exception:
            pass

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MEDIA_DIR = os.path.join(os.path.dirname(__file__), "media")
os.makedirs(MEDIA_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "")
WA_APP_SECRET = os.getenv("WA_APP_SECRET", "")

if not WA_VERIFY_TOKEN or not WA_APP_SECRET:
    print("[WARN] Missing WA_VERIFY_TOKEN or WA_APP_SECRET; WhatsApp webhook will fail verification.")

@app.get("/health", response_class=PlainTextResponse)
async def health():
    return "OK"

from api.chat import router as chat_router
from api.image_analyzer import router as image_router
from api.document_mailer import router as mail_router
from api.tata_search import router as search_router
from api.tata_chat import router as tata_chat_router
from api.avatar import router as avatar_router

app.include_router(chat_router, prefix="/api")
app.include_router(image_router, prefix="/api")
app.include_router(mail_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(tata_chat_router, prefix="/api")
app.include_router(avatar_router, prefix="/api")

# util to verify webhook signatures
def _verify_whatsapp_signature(signature_header: str | None, raw_body: bytes) -> bool:
    if not signature_header or not WA_APP_SECRET:
        return False
 
    try:
        algo, hexdigest = signature_header.split("=", 1)
        if algo != "sha256":
            return False
    except ValueError:
        return False
    expected = hmac.new(WA_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()

    return hmac.compare_digest(hexdigest, expected)

@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    print(f"🔍 Mode: {mode}, Token: {token}, Challenge: {challenge}")
    if mode == "subscribe" and token == WA_VERIFY_TOKEN:
        return PlainTextResponse(content=challenge, status_code=200)
    return PlainTextResponse("Verification failed", status_code=403)

from utils.wa import wa_client
from utils.agent_bridge import tata_reply

@app.post("/webhook")
async def whatsapp_receive(request: Request):
    signature = request.headers.get("x-hub-signature-256")
    raw = await request.body()
    if not _verify_whatsapp_signature(signature, raw):
        raise HTTPException(status_code=401, detail="Bad signature")

    data = await request.json()

    try:
        changes = data["entry"][0]["changes"][0]["value"]

        # Ignore delivery/read callbacks cleanly
        if "statuses" in changes:
            return {"ok": True}

        msgs = changes.get("messages", [])
        for m in msgs:
            sender = m.get("from")  # E.164 like "91XXXXXXXXXX"
            mtype = m.get("type")

            # Normalize inbound text across message types
            text = None
            if mtype == "text":
                text = (m.get("text") or {}).get("body", "").strip()
            elif mtype == "interactive":
                inter = m.get("interactive") or {}
                if inter.get("type") == "button_reply":
                    text = inter["button_reply"]["title"]
                elif inter.get("type") == "list_reply":
                    text = inter["list_reply"]["title"]
            elif mtype == "image":
                # Optional: acknowledge; you can fetch media later via Graph API
                text = "[image received]"

            if not (sender and text):
                continue

            # Call your Tata agent and send the reply
            try:
                bot_reply = await tata_reply(text)
            except Exception as e:
                print(f"[AGENT] tata_reply error: {e}")
                bot_reply = "Sorry, I'm having trouble answering that right now."

            await wa_client.send_text(sender, bot_reply)

        return {"ok": True}
    except Exception as e:
        # Never 5xx the webhook; log and return ok so Meta doesn't retry forever
        print(f"[WA] Webhook parse error: {e}")
        return {"ok": True, "note": "ignored non-message update"}


@app.post("/admin/reindex")
def reindex():
    csv_path = Path("assets/Tata Sampann Product Details - Sheet1.csv")
    if not csv_path.exists():
        raise HTTPException(400, "assets/Tata Sampann Product Details - Sheet1.csv missing")
    ingest(csv_path)
    return {"status": "ok"}

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/oauth/google/callback")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
SCOPES_STR = " ".join(SCOPES)

def _ensure_oauth_env():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_REDIRECT_URI:
        raise HTTPException(500, "Missing GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI in environment.")

@app.get("/oauth/google/start")
def google_oauth_start():
    _ensure_oauth_env()
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES_STR,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return RedirectResponse(url)

@app.get("/oauth/google/callback", response_class=HTMLResponse)
async def google_oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
    _ensure_oauth_env()
    if error:
        raise HTTPException(400, f"OAuth error: {error}")
    if not code:
        raise HTTPException(400, "Missing 'code' in callback.")
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(token_url, data=data)
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"Token exchange failed: {resp.text}")
    tokens = resp.json()
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")
    if not refresh_token:
        return HTMLResponse(
            "<h2>No refresh_token returned</h2>"
            "<p>Revoke prior access at "
            "<a href='https://myaccount.google.com/permissions' target='_blank'>"
            "Google Account → Security → Third-party access</a> and try again.</p>"
        )
    return HTMLResponse(
        "<h2>Google OAuth successful</h2>"
        "<p><b>Refresh token (save securely):</b></p>"
        f"<pre style='white-space:pre-wrap;word-break:break-all'>{refresh_token}</pre>"
        "<p>Access token (temporary):</p>"
        f"<pre style='white-space:pre-wrap;word-break:break-all'>{access_token}</pre>"
        "<p>After saving the refresh token, remove this page/route.</p>"
    )

@app.post("/api/chat-agent/poll-now")
async def chat_poll_now():
    try:
        summary = await chat_agent.poll_once()
        return {"ok": True, "summary": summary}
    except Exception as e:
        raise HTTPException(500, f"Chat poll failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)