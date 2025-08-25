import os
import re
import base64
import asyncio
from typing import Any, Dict, List, Optional, Tuple
import httpx
from motor.motor_asyncio import AsyncIOMotorClient

USE_OPENAI = os.environ.get("USE_OPENAI", "true").lower() == "true"
OPENAI_MODEL = (
     os.environ.get("OPENAI_VISION_MODEL")
    or "gpt-4o-mini"
)

try:
    from openai import OpenAI 
    _openai_client = OpenAI() if USE_OPENAI else None
except Exception:
    _openai_client = None
    USE_OPENAI = False

# ----------------------------
# Google / Gmail config
# ----------------------------
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
GOOGLE_REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]

GMAIL_SENDER = os.environ.get("GMAIL_SENDER", "support.ai@diffrun.com")
GMAIL_SEARCH_QUERY = os.environ.get(
    "GMAIL_SEARCH_QUERY",
    "in:inbox -from:me newer_than:2d -category:{promotions social} -label:Agent/Autoreplied",
)

LABEL_AUTOREPLIED = os.environ.get("LABEL_AUTOREPLIED", "Agent/Autoreplied")
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "90"))

# ----------------------------
# Mongo config (read-only)
# ----------------------------
MONGO_URI = os.environ["MONGODB_URI_READONLY"]
MONGO_DB_NAME = os.environ.get("MONGODB_DB_NAME", "app")
COL_ORDERS = os.environ.get("MONGODB_COLLECTION_ORDERS", os.environ.get("MONGODB_COLLECTION", "orders"))
COL_JOBS = os.environ.get("MONGODB_COLLECTION_JOBS", COL_ORDERS)

# Try multiple field names when searching
ORDER_ID_FIELDS = [s.strip() for s in os.environ.get("ORDER_ID_FIELDS", "order_id,orderId,orderNumber,id").split(",") if s.strip()]
JOB_ID_FIELDS = [s.strip() for s in os.environ.get("JOB_ID_FIELDS", "job_id,jobId").split(",") if s.strip()]

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


def extract_text_from_payload(payload: Dict[str, Any]) -> Tuple[str, str]:
    mime = payload.get("mimeType", "")
    if not mime.startswith("multipart/"):
        body_data = payload.get("body", {}).get("data")
        if body_data:
            raw = b64url_decode(body_data).decode("utf-8", errors="ignore")
            if mime == "text/plain":
                return raw, ""
            elif mime == "text/html":
                return "", raw
    text_plain, text_html = "", ""
    parts = payload.get("parts", []) or []
    for part in parts:
        p_mime = part.get("mimeType", "")
        p_data = part.get("body", {}).get("data")
        if not p_data:
            if p_mime.startswith("multipart/") and part.get("parts"):
                nested_plain, nested_html = extract_text_from_payload(part)
                text_plain = text_plain or nested_plain
                text_html = text_html or nested_html
            continue
        decoded = b64url_decode(p_data).decode("utf-8", errors="ignore")
        if p_mime == "text/plain" and not text_plain:
            text_plain = decoded
        elif p_mime == "text/html" and not text_html:
            text_html = decoded
        if text_plain and text_html:
            break
    return text_plain, text_html


def strip_quotes_and_signature(text: str) -> str:
    cut_markers = ["\nOn ", "-----Original Message-----", "\n> "]
    cut_idx = len(text)
    for m in cut_markers:
        i = text.find(m)
        if i != -1:
            cut_idx = min(cut_idx, i)
    text = text[:cut_idx]
    sig_idx = text.find("\n-- \n")
    if sig_idx != -1:
        text = text[:sig_idx]
    return text.strip()


# --- ID extraction (improved) ---

UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# Order ID patterns:
# 1) labeled numeric or code after "order"/"order id"/"order #"
ORDER_LABELED_RE = re.compile(
    r"""(?ix)
    \border            # word 'order'
    (?:\s*(?:id|no|number))?   # optional 'id/no/number'
    \s*(?:[:#])?\s*            # optional ':' or '#'
    ["']?\s*                   # optional quote
    (                          # capture:
       [A-Z]{2,6}-\d{2,10}     # e.g., ABC-1234
      |#?\d{3,12}              # or #1593 / 1593 (3-12 digits)
      |[A-Z0-9-]{3,}           # or generic code
    )
    """,
)

# 2) standalone hash-number if near 'order' word (secondary pass)
HASH_NUMBER_RE = re.compile(r"#\s?(\d{3,12})")

def clean_id_token(s: str) -> str:
    return s.strip().strip('"\'')

def extract_ids(subject: str, body: str) -> Tuple[Optional[str], Optional[str]]:
    text = f"{subject}\n{body}"
    # job id (UUID) anywhere
    job = None
    mjob = UUID_RE.search(text)
    if mjob:
        job = clean_id_token(mjob.group(0))

    # order id: prefer labeled forms
    order = None
    m1 = ORDER_LABELED_RE.search(text)
    if m1:
        token = clean_id_token(m1.group(1))
        if token.startswith("#"):
            token = token.lstrip("#")
        order = token.upper()
    else:
        # fallback: hash-number if 'order' is mentioned nearby
        if "order" in text.lower():
            m2 = HASH_NUMBER_RE.search(text)
            if m2:
                order = m2.group(1).upper()

    return order, job


def build_reply_mime(
    sender: str,
    to_addr: str,
    subject: str,
    in_reply_to: str,
    references: str,
    body_text: str,
) -> str:
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
# Gmail API client
# ----------------------------

class GmailClient:
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API_BASE = "https://gmail.googleapis.com/gmail/v1"

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
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(self.TOKEN_URL, data=data)
        r.raise_for_status()
        self._access_token = r.json()["access_token"]
        return self._access_token

    async def _auth_header(self) -> Dict[str, str]:
        if not self._access_token:
            await self._refresh_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    async def list_messages(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        headers = await self._auth_header()
        params = {"q": query, "maxResults": max_results}
        url = f"{self.API_BASE}/users/me/messages"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers=headers, params=params)
        if r.status_code == 401:
            await self._refresh_access_token()
            headers = await self._auth_header()
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(url, headers=headers, params=params)
        r.raise_for_status()
        return r.json().get("messages", []) or []

    async def get_message_full(self, message_id: str) -> Dict[str, Any]:
        headers = await self._auth_header()
        url = f"{self.API_BASE}/users/me/messages/{message_id}"
        params = {"format": "full"}
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers=headers, params=params)
        if r.status_code == 401:
            await self._refresh_access_token()
            headers = await self._auth_header()
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(url, headers=headers, params=params)
        r.raise_for_status()
        return r.json()

    async def send_reply_raw(self, thread_id: str, raw_base64url: str) -> Dict[str, Any]:
        headers = await self._auth_header()
        url = f"{self.API_BASE}/users/me/messages/send"
        payload = {"threadId": thread_id, "raw": raw_base64url}
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, headers=headers, json=payload)
        if r.status_code == 401:
            await self._refresh_access_token()
            headers = await self._auth_header()
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()

    async def list_labels(self) -> Dict[str, str]:
        if self._labels_cache:
            return self._labels_cache
        headers = await self._auth_header()
        url = f"{self.API_BASE}/users/me/labels"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers=headers)
        if r.status_code == 401:
            await self._refresh_access_token()
            headers = await self._auth_header()
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(url, headers=headers)
        r.raise_for_status()
        labels = r.json().get("labels", []) or []
        self._labels_cache = {lab["name"]: lab["id"] for lab in labels}
        return self._labels_cache

    async def add_labels_and_mark_read(self, message_id: str, label_names: List[str]) -> None:
        headers = await self._auth_header()
        labels_map = await self.list_labels()
        to_add = [labels_map[name] for name in label_names if name in labels_map]
        body = {"addLabelIds": to_add, "removeLabelIds": ["UNREAD"]}
        url = f"{self.API_BASE}/users/me/messages/{message_id}/modify"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, headers=headers, json=body)
        if r.status_code == 401:
            await self._refresh_access_token()
            headers = await self._auth_header()
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()

# ----------------------------
# DB helpers
# ----------------------------

async def _find_by_fields(col, value: str, fields: List[str]) -> Optional[Dict[str, Any]]:
    """
    Try multiple field names and (if numeric) both string and integer forms.
    """
    if value is None:
        return None
    v_clean = value.strip()
    candidates: List[Dict[str, Any]] = []
    # string comparisons
    for f in fields:
        candidates.append({f: v_clean})
    # if looks numeric, also try integer match
    if v_clean.isdigit():
        try:
            as_int = int(v_clean)
            for f in fields:
                candidates.append({f: as_int})
        except Exception:
            pass
    # Try each candidate in order
    for filt in candidates:
        doc = await col.find_one(filt, {"_id": 0})
        if doc:
            return doc
    return None

# ----------------------------
# LLM rephrase (optional)
# ----------------------------

async def _rephrase_with_openai(order_id: Optional[str], job_id: Optional[str],
                                order_doc: Optional[Dict[str, Any]],
                                job_doc: Optional[Dict[str, Any]],
                                fallback_text: str) -> str:
    if not USE_OPENAI or not _openai_client:
        return fallback_text
    # Build strict content – ONLY pass facts
    facts: Dict[str, Any] = {"order_id": order_id, "job_id": job_id, "order": order_doc, "job": job_doc}
    try:
        resp = _openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Diffrun Support. Write a concise, friendly email reply using ONLY the facts provided. "
                        "Do not invent details. If a field is missing, say so briefly and ask for it. "
                        "Prefer bullet points only if multiple items are present. Keep it under 120 words."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Compose an email reply from these facts:\n"
                        f"{facts}\n\n"
                        "Include the order id and job id if present, current status, dates/ETA if present. "
                        "Do not add any data not shown above."
                    ),
                },
                {"role": "assistant", "content": f"Draft (fallback to use if unsure):\n{fallback_text}"},
            ],
        )
        text = resp.choices[0].message.content.strip()
        # Safety: if LLM returned empty or added URLs, fall back
        if not text:
            return fallback_text
        return text
    except Exception as e:
        print(f"[agent] OpenAI error; using fallback. {e}")
        return fallback_text


class GmailAutoReplyAgent:
    def __init__(self) -> None:
        self.gmail = GmailClient()
        mc = AsyncIOMotorClient(MONGO_URI)
        db = mc[MONGO_DB_NAME]
        self.col_orders = db[COL_ORDERS]
        self.col_jobs = db[COL_JOBS]
        self.seen_message_ids: set[str] = set()
        self._task: Optional[asyncio.Task] = None

    async def _build_reply_text(self, order_id: Optional[str], job_id: Optional[str]) -> Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Lookup order/job; return (fallback_text, order_doc, job_doc).
        """
        order_doc = await _find_by_fields(self.col_orders, order_id, ORDER_ID_FIELDS) if order_id else None
        job_doc = await _find_by_fields(self.col_jobs, job_id, JOB_ID_FIELDS) if job_id else None

        # Deterministic fallback text
        if order_doc or job_doc:
            lines = []
            if order_id:
                if order_doc:
                    status = order_doc.get("status", "processing")
                    placed = order_doc.get("placed_at") or order_doc.get("created_at") or "-"
                    eta = order_doc.get("eta") or order_doc.get("delivery_eta") or "-"
                    lines.append(f"Order {order_id}: status {status}; placed {placed}; ETA {eta}.")
                else:
                    lines.append(f"Order {order_id}: not found.")
            if job_id:
                if job_doc:
                    jstatus = job_doc.get("status", "in progress")
                    updated = job_doc.get("updated_at") or "-"
                    lines.append(f"Job {job_id}: status {jstatus}; last update {updated}.")
                else:
                    lines.append(f"Job {job_id}: not found.")
            fallback = "Hello,\n\n" + "\n".join(lines) + "\n\nIf you need anything else, just reply to this email."
            return fallback, order_doc, job_doc

        # Nothing found
        missing_hint = []
        if order_id is None and job_id is None:
            missing_hint.append("your Order ID (e.g., ABC-1234 or 1593)")
            missing_hint.append("or your Job ID (UUID)")
        elif order_id and not order_doc:
            missing_hint.append(f"the exact Order ID (we couldn't find {order_id})")
        elif job_id and not job_doc:
            missing_hint.append(f"the exact Job ID (we couldn't find {job_id})")

        hint = "; ".join(missing_hint) if missing_hint else "the correct identifiers"
        fallback = (
            "Hello,\n\n"
            f"I couldn’t find matching records. Please share {hint}.\n"
            "We’ll check right away.\n"
        )
        return fallback, None, None

    async def _process_message(self, meta: Dict[str, Any]) -> None:
        message_id = meta.get("id", "")
        if not message_id or message_id in self.seen_message_ids:
            return
        msg = await self.gmail.get_message_full(message_id)
        thread_id = msg.get("threadId", "")
        payload = msg.get("payload", {}) or {}
        headers = payload.get("headers", []) or []
        subject = pick_header(headers, "Subject") or ""
        from_header = pick_header(headers, "From") or ""
        msg_id_header = pick_header(headers, "Message-ID") or pick_header(headers, "Message-Id") or ""

        text_plain, text_html = extract_text_from_payload(payload)
        body_top = strip_quotes_and_signature(text_plain or text_html)

        # ---- improved extraction ----
        order_id, job_id = extract_ids(subject, body_top)

        # ---- DB lookups + fallback text ----
        fallback_text, order_doc, job_doc = await self._build_reply_text(order_id, job_id)

        # ---- optional OpenAI rephrase (facts only) ----
        final_text = await _rephrase_with_openai(order_id, job_id, order_doc, job_doc, fallback_text)

        raw = build_reply_mime(
            sender=GMAIL_SENDER,
            to_addr=from_header,
            subject=subject,
            in_reply_to=msg_id_header or "<unknown>",
            references=msg_id_header or "<unknown>",
            body_text=final_text,
        )
        await self.gmail.send_reply_raw(thread_id=thread_id, raw_base64url=raw)
        await self.gmail.add_labels_and_mark_read(message_id=message_id, label_names=[LABEL_AUTOREPLIED])
        self.seen_message_ids.add(message_id)

    async def poll_once(self) -> Dict[str, Any]:
        metas = await self.gmail.list_messages(query=GMAIL_SEARCH_QUERY, max_results=10)
        processed = 0
        for m in metas:
            try:
                await self._process_message(m)
                processed += 1
            except httpx.HTTPStatusError as e:
                print(f"[agent] HTTP error for message {m.get('id')}: {e.response.status_code} {e.response.text}")
            except Exception as e:
                print(f"[agent] Error processing message {m.get('id')}: {e}")
        return {"listed": len(metas), "processed": processed}

    async def _loop(self) -> None:
        print(f"[agent] Polling started, every {POLL_INTERVAL_SECONDS}s. Query='{GMAIL_SEARCH_QUERY}'")
        while True:
            try:
                summary = await self.poll_once()
                print(f"[agent] summary: {summary}")
            except Exception as e:
                print(f"[agent] loop error: {e}")
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

agent = GmailAutoReplyAgent()