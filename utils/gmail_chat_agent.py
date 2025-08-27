# utils/gmail_chat_agent.py
import os
import io
import re
import time
import json
import base64
import hashlib
import logging
import threading
import asyncio
import requests
from datetime import datetime, timezone
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

try:
    from PyPDF2 import PdfReader
    _USE_PYPDF2 = True
except Exception:
    _USE_PYPDF2 = False

USE_OPENAI = os.environ.get("USE_OPENAI", "true").lower() == "true"
OPENAI_MODEL = (
    os.environ.get("OPENAI_MODEL")
    or os.environ.get("OPENAI_VISION_MODEL")
    or "gpt-4o-mini"
)
try:
    from openai import OpenAI
    _openai = OpenAI() if USE_OPENAI else None
except Exception:
    _openai = None
    USE_OPENAI = False

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN", "")

GMAIL_SENDER = os.environ.get("GMAIL_SENDER", "support.ai@diffrun.com")

_RAW_GMAIL_CHAT_QUERY = os.environ.get(
    "GMAIL_CHAT_QUERY",
    'in:inbox is:unread has:attachment filename:pdf -from:me newer_than:7d '
    '-category:{promotions social} -label:"Agent/Chatted" -label:"Agent/Processing" -label:"Agent/PDFDone"'
)

CHAT_DONE_LABEL = os.environ.get("CHAT_DONE_LABEL", "Agent/Chatted")
LOCK_LABEL = os.environ.get("LOCK_LABEL", "Agent/Processing")
DONE_LABEL = os.environ.get("DONE_LABEL", "Agent/PDFDone")

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "10"))
MAX_PAGES = int(os.environ.get("MAX_PAGES", "60"))
MAX_REPLY_CHARS = int(os.environ.get("MAX_REPLY_CHARS", "1800"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
INTENT_CHECK = os.environ.get("INTENT_CHECK", "true").lower() == "true"
REJECTION_MESSAGE = os.environ.get(
    "REJECTION_MESSAGE",
    "I only analyze attached PDFs. Please explicitly ask me to analyze/summarize the attachment."
)

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gmail_chat_agent")

INTENT_SYSTEM = (
    "ROLE: Intent classifier for an email agent that ONLY analyzes attached PDFs.\n"
    "INPUT: The user's email TEXT (never the PDF content).\n"
    "TASK: Decide if the user explicitly asks to analyze/summarize/extract information from the attached PDF.\n"
    "OUTPUT: EXACTLY one token: PDF_SUMMARY or OUT_OF_SCOPE.\n"
    "RULES:\n"
    "1) If the message is not explicitly about analyzing the attachment → OUT_OF_SCOPE.\n"
    "2) Greetings, chit-chat, coding help (JavaScript/Node/etc.), general Q&A, or ambiguity → OUT_OF_SCOPE.\n"
    "3) Do not infer intent. If unsure → OUT_OF_SCOPE.\n"
    "4) Only if the text clearly says to analyze/summarize/extract from the attachment → PDF_SUMMARY.\n"
)

SUMMARY_SYSTEM = (
    "You analyze ONLY the provided PDF text. Do not use outside knowledge. "
    "If something is not in the text, respond 'Not stated'. "
    "Cite page numbers like (p.5). Be concise, executive-ready, and strictly grounded in the provided text."
)

def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</p>", "\n", html)
    html = re.sub(r"(?is)<.*?>", " ", html)
    return re.sub(r"[ \t]+", " ", html).strip()

def _make_safe_query(q: str) -> str:
    tokens = q.split()
    have = set(tokens)
    need = ["has:attachment", "filename:pdf"]
    for tkn in need:
        if tkn not in have:
            tokens.append(tkn)
    if "in:inbox" not in have:
        tokens.insert(0, "in:inbox")
    if "is:unread" not in have:
        tokens.append("is:unread")
    if "-from:me" not in have:
        tokens.append("-from:me")
    if not any(t.startswith("newer_than:") for t in tokens):
        tokens.append("newer_than:7d")
    if "-category:{promotions" not in q:
        tokens.append("-category:{promotions social}")
    excludes = [f'-label:"{LOCK_LABEL}"', f'-label:"{DONE_LABEL}"', f'-label:"{CHAT_DONE_LABEL}"']
    for ex in excludes:
        if ex not in q:
            tokens.append(ex)
    seen, out = set(), []
    for t in tokens:
        if t not in seen:
            out.append(t); seen.add(t)
    return " ".join(out)

GMAIL_CHAT_QUERY = _make_safe_query(_RAW_GMAIL_CHAT_QUERY)

def _get_access_token() -> str:
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": GOOGLE_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"OAuth token error: {resp.status_code} {resp.text}")
    return resp.json()["access_token"]

def _gmail_get(path: str, token: str, params: dict | None = None) -> dict:
    r = requests.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Gmail GET {path}: {r.status_code} {r.text}")
    return r.json()

def _gmail_post(path: str, token: str, payload: dict) -> dict:
    r = requests.post(
        f"https://gmail.googleapis.com/gmail/v1/users/me/{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=30,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Gmail POST {path}: {r.status_code} {r.text}")
    return r.json()

def _gmail_modify_labels(msg_id: str, add: list[str] | None, remove: list[str] | None, token: str) -> None:
    _gmail_post(f"messages/{msg_id}/modify", token, {"addLabelIds": add or [], "removeLabelIds": remove or []})

def _gmail_list_messages(token: str, query: str, max_results: int = 5) -> list[dict]:
    data = _gmail_get("messages", token, params={"q": query, "maxResults": max_results})
    return data.get("messages", [])

def _gmail_get_message(token: str, msg_id: str) -> dict:
    return _gmail_get(f"messages/{msg_id}", token, params={"format": "full"})

def _gmail_get_attachment(token: str, msg_id: str, att_id: str) -> bytes:
    data = _gmail_get(f"messages/{msg_id}/attachments/{att_id}", token)
    return _b64url_decode(data["data"])

def _gmail_ensure_label(token: str, name: str) -> str:
    labels = _gmail_get("labels", token).get("labels", [])
    for lab in labels:
        if lab.get("name") == name:
            return lab["id"]
    created = _gmail_post("labels", token, {"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"})
    return created["id"]

def _gmail_send_reply(token: str, thread_id: str, in_reply_to_msg_id: str, to_addr: str, subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["To"] = to_addr
    msg["From"] = GMAIL_SENDER
    msg["Subject"] = f"Re: {subject}" if not subject.lower().startswith("re:") else subject
    if in_reply_to_msg_id:
        msg["In-Reply-To"] = in_reply_to_msg_id
        msg["References"] = in_reply_to_msg_id
    msg.set_content(body[:MAX_REPLY_CHARS])
    raw = _b64url_encode(msg.as_bytes())
    res = _gmail_post("messages/send", token, {"raw": raw, "threadId": thread_id})
    return res["id"]

def _get_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""

def _collect_text(parts: list[dict]) -> tuple[str, str]:
    plain, html = [], []
    for p in parts:
        mime = p.get("mimeType", "")
        body = p.get("body", {}) or {}
        data = body.get("data", "")
        text = _b64url_decode(data).decode("utf-8", errors="ignore") if data else ""
        if mime.startswith("text/plain"):
            if text.strip():
                plain.append(text)
        elif mime.startswith("text/html"):
            if text.strip():
                html.append(text)
        elif "parts" in p:
            c_plain, c_html = _collect_text(p["parts"])
            if c_plain: plain.append(c_plain)
            if c_html: html.append(c_html)
    return ("\n".join(plain).strip(), "\n".join(html).strip())

def _extract_msg_text(msg: dict) -> str:
    payload = msg.get("payload", {}) or {}
    mime = payload.get("mimeType", "")
    body = payload.get("body", {}) or {}
    text_plain, text_html = "", ""
    if payload.get("parts"):
        text_plain, text_html = _collect_text(payload["parts"])
    else:
        data = body.get("data", "")
        text = _b64url_decode(data).decode("utf-8", errors="ignore") if data else ""
        if mime.startswith("text/html"):
            text_html = text
        else:
            text_plain = text
    text = text_plain or _strip_html(text_html) or ""
    text = re.split(r"\nOn .* wrote:\n", text, maxsplit=1)[0].strip()
    return text

def _classify_intent(message_text: str) -> str:
    if not INTENT_CHECK:
        return "PDF_SUMMARY"
    txt = (message_text or "").strip()
    if re.search(r"\b(teach|explain|how to|how do|node\.?js|javascript|python|code|error|bug|help me)\b", txt, re.I):
        return "OUT_OF_SCOPE"
    if not re.search(r"\b(pdf|document|report|statement|attachment|attached|file)\b", txt, re.I):
        if USE_OPENAI and _openai is not None:
            try:
                resp = _openai.chat.completions.create(
                    model=OPENAI_MODEL,
                    temperature=0,
                    max_tokens=4,
                    messages=[
                        {"role": "system", "content": INTENT_SYSTEM},
                        {"role": "user", "content": txt[:1500]},
                    ],
                )
                out = (resp.choices[0].message.content or "").strip().upper()
                if out in ("PDF_SUMMARY", "OUT_OF_SCOPE"):
                    return out
            except Exception:
                return "OUT_OF_SCOPE"
        return "OUT_OF_SCOPE"
    return "PDF_SUMMARY"

def _extract_pdf_pages(pdf_bytes: bytes) -> list[str]:
    if not _USE_PYPDF2:
        raise RuntimeError("Install PyPDF2")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if len(reader.pages) > MAX_PAGES:
        raise ValueError(f"PDF too large: {len(reader.pages)} pages (limit {MAX_PAGES})")
    out = []
    for i in range(len(reader.pages)):
        try:
            txt = (reader.pages[i].extract_text() or "").strip()
        except Exception:
            txt = ""
        out.append(txt)
    return out

def _summarize_pages(pages: list[str], filename: str) -> str:
    if not USE_OPENAI or _openai is None:
        joined = "\n".join([f"(p.{i+1}) {p[:400]}" for i, p in enumerate(pages) if p.strip()][:5])
        return f"Summary for {filename} (heuristic fallback):\n" + joined[:MAX_REPLY_CHARS]
    non_empty = [(i+1, p) for i, p in enumerate(pages) if p and p.strip()]
    if len(non_empty) > 12:
        head = non_empty[:8]
        tail = non_empty[-2:]
        mid = non_empty[len(non_empty)//2 - 1 : len(non_empty)//2 + 1]
        sample = head + mid + tail
    else:
        sample = non_empty
    chunks = []
    for pg, txt in sample:
        chunks.append(f"[Page {pg}]\n{txt[:3000]}")
    doc_text = "\n\n".join(chunks)
    user = (
        f"Document: {filename}\n"
        "Create an executive summary (120–180 words), then:\n"
        "• 5–8 key points with page cites\n"
        "• 3 risks/assumptions with page cites\n"
        "• 3 concrete action items\n\n"
        "Text follows:\n" + doc_text
    )
    resp = _openai.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    return (resp.choices[0].message.content or "")[:MAX_REPLY_CHARS]

def _find_first_pdf(msg: dict) -> tuple[str, str] | None:
    def walk(parts: list[dict]) -> tuple[str, str] | None:
        for part in parts:
            mime = part.get("mimeType", "")
            filename = (part.get("filename", "") or "").strip()
            body = part.get("body", {}) or {}
            if (mime == "application/pdf") or filename.lower().endswith(".pdf"):
                att_id = body.get("attachmentId")
                if att_id:
                    return filename or "document.pdf", att_id
            if "parts" in part:
                r = walk(part["parts"])
                if r:
                    return r
        return None
    payload = msg.get("payload", {}) or {}
    if payload.get("parts"):
        return walk(payload["parts"])
    if (payload.get("mimeType") == "application/pdf") and payload.get("body", {}).get("attachmentId"):
        return (payload.get("filename") or "document.pdf", payload["body"]["attachmentId"])
    return None

def _process_one_email(token: str) -> dict | None:
    msgs = _gmail_list_messages(token, GMAIL_CHAT_QUERY, max_results=5)
    if not msgs:
        return None
    lock_id = _gmail_ensure_label(token, LOCK_LABEL)
    pdf_done_id = _gmail_ensure_label(token, DONE_LABEL)
    chatted_id = _gmail_ensure_label(token, CHAT_DONE_LABEL)
    for m in msgs:
        msg = _gmail_get_message(token, m["id"])
        lbls = set(msg.get("labelIds") or [])
        if lock_id in lbls or pdf_done_id in lbls or chatted_id in lbls:
            continue
        pdf_meta = _find_first_pdf(msg)
        if not pdf_meta:
            continue
        _gmail_modify_labels(m["id"], add=[lock_id], remove=None, token=token)
        try:
            thread_id = msg.get("threadId")
            headers = msg.get("payload", {}).get("headers", []) or []
            subj = _get_header(headers, "Subject") or "(no subject)"
            from_addr = _get_header(headers, "From")
            to_addr = (from_addr.split("<")[-1].rstrip(">") or "").strip() or from_addr
            msg_id_hdr = _get_header(headers, "Message-ID") or _get_header(headers, "Message-Id") or ""
            message_text = _extract_msg_text(msg)
            intent = _classify_intent(message_text)
            filename, att_id = pdf_meta
            if intent != "PDF_SUMMARY":
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                body = f"{REJECTION_MESSAGE}\n\n—\nRef: {m['id'][:12]} • {stamp}"
                _gmail_send_reply(token, thread_id, msg_id_hdr, to_addr, subj, body)
                _gmail_modify_labels(m["id"], add=[chatted_id], remove=[lock_id], token=token)
                return {"message_id": m["id"], "action": "rejected", "subject": subj}
            pdf_bytes = _gmail_get_attachment(token, m["id"], att_id)
            sha = _sha256_hex(pdf_bytes)
            pages = _extract_pdf_pages(pdf_bytes)
            summary = _summarize_pages(pages, filename)
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            body = f"Here’s a concise analysis of '{filename}':\n\n{summary}\n\n—\nRef: {sha[:12]} • {stamp}"
            _gmail_send_reply(token, thread_id, msg_id_hdr, to_addr, subj, body)
            _gmail_modify_labels(m["id"], add=[pdf_done_id], remove=[lock_id], token=token)
            return {"message_id": m["id"], "action": "summarized", "subject": subj, "pages": len(pages)}
        except Exception:
            try:
                _gmail_modify_labels(m["id"], add=None, remove=[lock_id], token=token)
            except Exception:
                pass
            continue
    return None

class GmailChatAgent:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN):
            raise RuntimeError("Missing Google OAuth env vars.")
        if not _USE_PYPDF2:
            raise RuntimeError("Install PyPDF2")
        if self._thread and self._thread.is_alive():
            return
        log.info("Agent loop starting with query=%r", GMAIL_CHAT_QUERY)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="gmail-chat-agent", daemon=True)
        self._thread.start()

    async def stop(self):
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            for _ in range(50):
                if not t.is_alive():
                    break
                await asyncio.sleep(0.1)

    def _run_loop(self):
        while not self._stop.is_set():
            try:
                token = _get_access_token()
                res = _process_one_email(token)
                if not res:
                    time.sleep(POLL_INTERVAL_SECONDS)
            except Exception:
                time.sleep(POLL_INTERVAL_SECONDS)

    async def poll_once(self) -> dict:
        token = _get_access_token()
        res = await asyncio.to_thread(_process_one_email, token)
        return res or {"message": "no-op"}

chat_agent = GmailChatAgent()
