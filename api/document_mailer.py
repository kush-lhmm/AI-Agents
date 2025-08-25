import os
import mimetypes
from email.message import EmailMessage
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

# ----- Config (env vars or sane defaults) -----
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")             # or use AWS_DEFAULT_REGION
SES_FROM   = os.getenv("SES_FROM", "kush@lhmm.in")             # must be verified in SES
S3_BUCKET  = os.getenv("S3_BUCKET", "testing-bucket-agent")

# Raw file-size cap before we even consider attaching (you can set to 50 if you want)
ATTACH_LIMIT_RAW_MB    = int(os.getenv("ATTACH_LIMIT_RAW_MB", "30"))
PRESIGN_EXPIRY_SECONDS = int(os.getenv("PRESIGN_EXPIRY_SECONDS", str(48 * 3600)))

# SES total MIME size cap (~40 MB). Keep conservative; SES enforces on the encoded message.
SES_MAX_MIME_BYTES = 40 * 1024 * 1024

# Conservative recipient caps (Gmail/Outlook ~25 MB)
DEFAULT_INBOUND_LIMIT = 25 * 1024 * 1024

# ----- AWS clients -----
s3    = boto3.client("s3",    region_name=AWS_REGION)
sesv2 = boto3.client("sesv2", region_name=AWS_REGION)

# ----- Optional code -> filename map -----
CODE_MAP = {
    "itc-2019":         "itc-integrated-report-2019.pdf",
    "itc-2024-report":  "20250602itcannual-report-2024webpagesrpdf.pdf",
    "itc-sera":         "ITC_27062025151216_SERA.pdf",
    "itc-food-policy":  "itc-food-division-marketing-and-communication-policy.pdf",
    "itc-results-2024": "Results_23052024140736.pdf",
}

class SendMailPayload(BaseModel):
    to: EmailStr
    code: Optional[str] = None
    filename: Optional[str] = None

router = APIRouter(prefix="", tags=["document-mailer"])

# ---------- helpers ----------
def _resolve_key(p: SendMailPayload) -> str:
    if p.code:
        if p.code not in CODE_MAP:
            raise HTTPException(400, f"Unknown code: {p.code}")
        return CODE_MAP[p.code]
    if p.filename:
        return p.filename
    raise HTTPException(400, "Provide either 'code' or 'filename'.")

def _presigned_url(key: str) -> str:
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=PRESIGN_EXPIRY_SECONDS,
    )

def _estimate_mime_bytes(size_bytes: int) -> int:
    # Base64 expansion ~4/3 + ~100KB for MIME headers
    return int(size_bytes * 4 / 3) + 100 * 1024

def _recipient_inbound_limit(to_addr: str) -> int:
    domain = to_addr.split("@")[-1].lower()
    if domain in {"gmail.com", "googlemail.com",
                  "outlook.com", "hotmail.com", "live.com", "msn.com", "outlook.in"}:
        return 25 * 1024 * 1024
    return DEFAULT_INBOUND_LIMIT

def _can_attach(size_bytes: int, to_addr: str) -> bool:
    # 1) SES encoded cap
    if _estimate_mime_bytes(size_bytes) > SES_MAX_MIME_BYTES:
        return False
    # 2) Recipient inbound cap (e.g., Gmail 25MB)
    if _estimate_mime_bytes(size_bytes) > _recipient_inbound_limit(to_addr):
        return False
    # 3) Your raw cap (tunable)
    return size_bytes <= ATTACH_LIMIT_RAW_MB * 1024 * 1024

def _raw_email_with_attachment(
    to_addr: str, subject: str, body_text: str,
    att_name: str, att_bytes: bytes, mime_type: str
) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = SES_FROM
    msg["To"]      = to_addr
    msg.set_content(body_text)
    maintype, subtype = (mime_type.split("/", 1)
                         if "/" in mime_type else ("application", "octet-stream"))
    msg.add_attachment(att_bytes, maintype=maintype, subtype=subtype, filename=att_name)
    return msg.as_bytes()

# ---------- routes ----------
@router.get("/mail/codes")
def list_codes():
    return {"codes": CODE_MAP}

@router.post("/mail/send")
def send_mail(p: SendMailPayload):
    key = _resolve_key(p)

    # Confirm object & get size
    try:
        head = s3.head_object(Bucket=S3_BUCKET, Key=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            raise HTTPException(404, f"File not found in S3: {key}")
        raise

    size_bytes = head["ContentLength"]
    subject = f"Requested document: {os.path.basename(key)}"
    mime_type = mimetypes.guess_type(key)[0] or "application/octet-stream"

    attach_allowed = _can_attach(size_bytes, p.to)

    if attach_allowed:
        # Download and attach
        obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
        data = obj["Body"].read()
        raw = _raw_email_with_attachment(
            to_addr=p.to,
            subject=subject,
            body_text=f"Hey,\n\nAttaching the requested document: {os.path.basename(key)}\n\nRegards,\nTest Agent",
            att_name=os.path.basename(key),
            att_bytes=data,
            mime_type=mime_type,
        )
        try:
            resp = sesv2.send_email(
                FromEmailAddress=SES_FROM,
                Destination={"ToAddresses": [p.to]},
                Content={"Raw": {"Data": raw}},
            )
        except ClientError as e:
            # If recipient is suppressed/bounced, surface a clear 400
            err = e.response.get("Error", {})
            raise HTTPException(status_code=400, detail={"code": err.get("Code"), "message": err.get("Message")})
        return {
            "status": "sent",
            "mode": "attachment",
            "filename": key,
            "size_bytes": size_bytes,
            "message_id": resp.get("MessageId")
        }

    # Fallback to pre-signed link
    url = _presigned_url(key)
    html = f"""
        <p>Hey,</p>
        <p>Your requested document is available here (expires in {PRESIGN_EXPIRY_SECONDS // 3600}h):<br>
        <a href="{url}">{os.path.basename(key)}</a></p>
        <p>Regards,<br>Test Agent</p>
    """
    try:
        resp = sesv2.send_email(
            FromEmailAddress=SES_FROM,
            Destination={"ToAddresses": [p.to]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Html": {"Data": html, "Charset": "UTF-8"}}
                }
            },
        )
    except ClientError as e:
        err = e.response.get("Error", {})
        raise HTTPException(status_code=400, detail={"code": err.get("Code"), "message": err.get("Message")})
    return {
        "status": "sent",
        "mode": "link",
        "filename": key,
        "size_bytes": size_bytes,
        "message_id": resp.get("MessageId"),
        "link_expires_seconds": PRESIGN_EXPIRY_SECONDS
    }
