# utils/gmail_chat_agent.py
# Simple email chat agent: read new mails, build thread context, LLM reply, send.

import os
import re
import base64
import asyncio
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ----------------------------
# OpenAI (reply generation)
# ----------------------------
USE_OPENAI = os.environ.get("USE_OPENAI", "true").lower() == "true"
OPENAI_MODEL = (
    os.environ.get("OPENAI_MODEL")
    or os.environ.get("OPENAI_VISION_MODEL")
    or "gpt-4o-mini"
)
try:
    from openai import OpenAI  # openai>=1.0
    _openai = OpenAI() if USE_OPENAI else None  # reads OPENAI_API_KEY from env
except Exception:
    _openai = None
    USE_OPENAI = False

# ----------------------------
# Gmail / Google config
# ----------------------------
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
GOOGLE_REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]

GMAIL_SENDER = os.environ.get("GMAIL_SENDER", "support.ai@diffrun.com")

# Only chat agent’s search (kept separate from your DB agent)
GMAIL_CHAT_QUERY = os.environ.get(
    "GMAIL_CHAT_QUERY",
    "in:inbox -from:me newer_than:2d -category:{promotions social} -label:Agent/Chatted",
)

CHAT_DONE_LABEL = os.environ.get("CHAT_DONE_LABEL", "Agent/Chatted")
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "10"))

# Chat tuning
CHAT_MAX_HISTORY = int(os.environ.get("CHAT_MAX_HISTORY", "6"))  # last N messages from thread
CHAT_SYSTEM_PROMPT = os.environ.get(
    "CHAT_SYSTEM_PROMPT",
    "You are Diffrun Email Assistant. Reply helpfully and concisely in plain text. "
    "Use the thread context only; do not invent facts. Keep under 120 words. No links unless present in the thread.",
)

# ----------------------------
# Helpers
# ----------------------------
def b64url_decode(data: str) -> bytes:
    s = data.replace("-", "+").replace("_", "/")
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    return base64.b64decode(s + pad)

def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def pick_header(headers: List[Dict[str, str]], name: str) -> Optional[str]:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None

def extract_text_from_payload(payload: Dict[str, Any]) -> str:
    """Prefer text/plain; fallback to text/html (tags removed crudely)."""
    mime = payload.get("mimeType", "")
    if not mime.startswith("multipart/"):
        data = payload.get("body", {}).get("data")
        if data:
            raw = b64url_decode(data).decode("utf-8", errors="ignore")
            return raw
        return ""
    text_plain, text_html = "", ""
    parts = payload.get("parts", []) or []
    for part in parts:
        pmime = part.get("mimeType", "")
        pdata = part.get("body", {}).get("data")
        if not pdata:
            if pmime.startswith("multipart/") and part.get("parts"):
                nested = extract_text_from_payload(part)
                if nested and not text_plain:
                    text_plain = nested
            continue
        decoded = b64url_decode(pdata).decode("utf-8", errors="ignore")
        if pmime == "text/plain" and not text_plain:
            text_plain = decoded
        elif pmime == "text/html" and not text_html:
            text_html = re.sub(r"<[^>]+>", " ", decoded)  # strip tags
        if text_plain and text_html:
            break
    return text_plain or text_html or ""

def strip_quotes(text: str) -> str:
    """Drop quoted history/signature; keep the new chunk."""
    cuts = ["\nOn ", "-----Original Message-----", "\n> "]
    cut = min([text.find(m) for m in cuts if m in text] + [len(text)])
    text = text[:cut]
    sig = text.find("\n-- \n")
    if sig != -1:
        text = text[:sig]
    return re.sub(r"\s+\n", "\n", text.strip())

def build_reply_mime(sender: str, to_addr: str, subject: str,
                     in_reply_to: str, references: str, body_text: str) -> str:
    subj = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    mime = (
        f"From: {sender}\r\n"
        f"To: {to_addr}\r\n"
        f"Subject: {subj}\r\n"
        f"In-Reply-To: {in_reply_to}\r\n"
        f"References: {references}\r\n"
        f"Content-Type: text/plain; charset=\"UTF-8\"\r\n"
        f"Content-Transfer-Encoding: 7bit\r\n"
        f"\r\n"
        f"{body_text}\r\n"
    )
    return b64url_encode(mime.encode("utf-8"))

# ----------------------------
# Gmail client (minimal)
# ----------------------------
class GmailClient:
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API_BASE  = "https://gmail.googleapis.com/gmail/v1"

    def __init__(self) -> None:
        self._access_token: Optional[str] = None
        self._labels_cache: Dict[str, str] = {}

    async def _refresh_access_token(self) -> str:
        data = {
            "grant_type": "refresh_token",
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": GOOGLE_REFRESH_TOKEN,
        }
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(self.TOKEN_URL, data=data)
        r.raise_for_status()
        self._access_token = r.json()["access_token"]
        return self._access_token

    async def _auth(self) -> Dict[str, str]:
        if not self._access_token:
            await self._refresh_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    async def list_messages(self, q: str, max_results: int = 10) -> List[Dict[str, Any]]:
        h = await self._auth()
        u = f"{self.API_BASE}/users/me/messages"
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(u, headers=h, params={"q": q, "maxResults": max_results})
        if r.status_code == 401:
            await self._refresh_access_token()
            h = await self._auth()
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(u, headers=h, params={"q": q, "maxResults": max_results})
        r.raise_for_status()
        return r.json().get("messages", []) or []

    async def get_message_full(self, msg_id: str) -> Dict[str, Any]:
        h = await self._auth()
        u = f"{self.API_BASE}/users/me/messages/{msg_id}"
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(u, headers=h, params={"format": "full"})
        if r.status_code == 401:
            await self._refresh_access_token()
            h = await self._auth()
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(u, headers=h, params={"format": "full"})
        r.raise_for_status()
        return r.json()

    async def get_thread_full(self, thread_id: str) -> Dict[str, Any]:
        h = await self._auth()
        u = f"{self.API_BASE}/users/me/threads/{thread_id}"
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(u, headers=h, params={"format": "full"})
        if r.status_code == 401:
            await self._refresh_access_token()
            h = await self._auth()
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(u, headers=h, params={"format": "full"})
        r.raise_for_status()
        return r.json()

    async def send_reply_raw(self, thread_id: str, raw: str) -> Dict[str, Any]:
        h = await self._auth()
        u = f"{self.API_BASE}/users/me/messages/send"
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(u, headers=h, json={"threadId": thread_id, "raw": raw})
        if r.status_code == 401:
            await self._refresh_access_token()
            h = await self._auth()
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(u, headers=h, json={"threadId": thread_id, "raw": raw})
        r.raise_for_status()
        return r.json()

    async def list_labels(self) -> Dict[str, str]:
        if self._labels_cache:
            return self._labels_cache
        h = await self._auth()
        u = f"{self.API_BASE}/users/me/labels"
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(u, headers=h)
        if r.status_code == 401:
            await self._refresh_access_token()
            h = await self._auth()
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(u, headers=h)
        r.raise_for_status()
        labs = r.json().get("labels", []) or []
        self._labels_cache = {L["name"]: L["id"] for L in labs}
        return self._labels_cache

    async def add_labels_and_mark_read(self, message_id: str, names: List[str]) -> None:
        h = await self._auth()
        labs = await self.list_labels()
        to_add = [labs[n] for n in names if n in labs]
        u = f"{self.API_BASE}/users/me/messages/{message_id}/modify"
        body = {"addLabelIds": to_add, "removeLabelIds": ["UNREAD"]}
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(u, headers=h, json=body)
        if r.status_code == 401:
            await self._refresh_access_token()
            h = await self._auth()
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(u, headers=h, json=body)
        r.raise_for_status()

# ----------------------------
# Chat agent
# ----------------------------
class GmailChatAgent:
    def __init__(self) -> None:
        self.gmail = GmailClient()
        self.seen_message_ids: set[str] = set()
        self._task: Optional[asyncio.Task] = None

    async def _thread_to_messages(self, thread: Dict[str, Any]) -> Tuple[List[Dict[str, str]], str, str, str, str]:
        """
        Convert a Gmail thread to OpenAI messages. Returns:
        (chat_messages, subject, last_from, last_message_id_header, thread_id)
        """
        msgs = thread.get("messages", []) or []
        # Sort by internalDate ascending
        msgs.sort(key=lambda m: int(m.get("internalDate", "0")))
        chat: List[Dict[str, str]] = []
        subject = ""
        last_from = ""
        last_msgid = ""
        for m in msgs[-CHAT_MAX_HISTORY:]:
            payload = m.get("payload", {}) or {}
            headers = payload.get("headers", []) or []
            from_h = pick_header(headers, "From") or ""
            subj_h = pick_header(headers, "Subject") or ""
            msgid_h = pick_header(headers, "Message-ID") or pick_header(headers, "Message-Id") or ""
            body = strip_quotes(extract_text_from_payload(payload))
            if subj_h:
                subject = subj_h  # last wins (same across thread)
            if body:
                role = "assistant" if GMAIL_SENDER.lower() in from_h.lower() else "user"
                chat.append({"role": role, "content": body[:4000]})
            last_from = from_h or last_from
            last_msgid = msgid_h or last_msgid
        return chat, subject, last_from, last_msgid, thread.get("id", "")

    async def _generate_reply(self, chat_messages: List[Dict[str, str]]) -> str:
        if not USE_OPENAI or not _openai:
            # Ultra-basic echo fallback
            last_user = next((m["content"] for m in reversed(chat_messages) if m["role"] == "user"), "")
            return f"Thanks for your message. You wrote:\n\n{last_user}\n\nHow can I help further?"
        resp = _openai.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.3,
            messages=[{"role": "system", "content": CHAT_SYSTEM_PROMPT}] + chat_messages,
        )
        return (resp.choices[0].message.content or "").strip()

    async def _process_message(self, meta: Dict[str, Any]) -> None:
        mid = meta.get("id", "")
        if not mid or mid in self.seen_message_ids:
            return
        # Get the message; then the full thread for context
        msg = await self.gmail.get_message_full(mid)
        thread_id = msg.get("threadId", "")
        thread = await self.gmail.get_thread_full(thread_id)
        chat_messages, subject, last_from, last_msgid, _ = await self._thread_to_messages(thread)

        # Only reply if the last message is NOT from us
        if GMAIL_SENDER.lower() in (last_from or "").lower():
            self.seen_message_ids.add(mid)
            return

        reply_text = await self._generate_reply(chat_messages)
        raw = build_reply_mime(
            sender=GMAIL_SENDER,
            to_addr=last_from,
            subject=subject or "Re: your email",
            in_reply_to=last_msgid or "<unknown>",
            references=last_msgid or "<unknown>",
            body_text=reply_text,
        )
        await self.gmail.send_reply_raw(thread_id=thread_id, raw=raw)
        await self.gmail.add_labels_and_mark_read(message_id=mid, names=[CHAT_DONE_LABEL])
        self.seen_message_ids.add(mid)

    async def poll_once(self) -> Dict[str, Any]:
        metas = await self.gmail.list_messages(q=GMAIL_CHAT_QUERY, max_results=10)
        processed = 0
        for m in metas:
            try:
                await self._process_message(m)
                processed += 1
            except httpx.HTTPStatusError as e:
                print(f"[chat-agent] HTTP {e.response.status_code}: {e.response.text}")
            except Exception as e:
                print(f"[chat-agent] error: {e}")
        return {"listed": len(metas), "processed": processed}

    async def _loop(self) -> None:
        print(f"[chat-agent] polling every {POLL_INTERVAL_SECONDS}s; query='{GMAIL_CHAT_QUERY}'")
        while True:
            try:
                summary = await self.poll_once()
                print(f"[chat-agent] {summary}")
            except Exception as e:
                print(f"[chat-agent] loop error: {e}")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    def start(self) -> None:
        if hasattr(self, "_task") and self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if hasattr(self, "_task") and self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

# Singleton
chat_agent = GmailChatAgent()