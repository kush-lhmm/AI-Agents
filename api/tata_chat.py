# api/tata_chat.py
from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

from api.tata_search import search as core_search
from api.prompt_loader import render_system_content
from api.query_prep import extract_filters  # we still use it, but we now expand queries too

# --------------------------- Init ---------------------------
load_dotenv()
router = APIRouter()

BASE_DIR = Path(__file__).resolve().parents[1]
TATA_PROMPT_PATH = BASE_DIR / "prompts" / "tata_system.json"
if not os.getenv("PROMPT_PATH"):
    if not TATA_PROMPT_PATH.exists():
        raise RuntimeError(f"Tata system prompt not found at: {TATA_PROMPT_PATH}")
    os.environ["PROMPT_PATH"] = str(TATA_PROMPT_PATH)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is not set")
client = OpenAI(api_key=api_key)

# ---------------------- Server-side defaults ----------------------
MODEL = "gpt-4.1-nano"
TEMPERATURE = 0.1

# Retrieval defaults (hidden from client)
K = 8
RANKER = "cross_encoder"      # will fall back if CE not installed
SORT = "relevance"
DISTINCT_BY_SKU = True
CE_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
CE_K = 40

# If your search records expose normalized "sim" (0..1), you can enable a cutoff.
MIN_SIM: Optional[float] = None  # e.g. 0.30

# --------------------------- I/O models ---------------------------
class ChatIn(BaseModel):
    message: str = Field(..., description="User message/question")
    class Config:
        extra = "ignore"  # ignore any extra fields the client might send


class ChatOut(BaseModel):
    reply: str
    used_results: List[Dict[str, Any]]
    meta: Dict[str, Any]


# --------------------------- Lexical helpers ---------------------------
GREETING_RE = re.compile(r"\b(hi|hey|hello|yo|namaste|good (morning|afternoon|evening))\b", re.I)
SMALLTALK_RE = re.compile(r"\b(how are you|what'?s up|thanks|thank you|help)\b", re.I)

def _tokens(s: str) -> List[str]:
    # keep basic latin/digits + devanagari as tokens, collapse others to space
    s = re.sub(r"[^\w\u0900-\u097F]+", " ", s.lower())
    return [t for t in s.split() if t]

# Hinglish/Hindi ↔ English product synonyms (+ plural/singular)
SYNONYMS: Dict[str, Set[str]] = {
    # nuts & seeds
    "kaju": {"cashew", "cashews", "kaju"},
    "badam": {"almond", "almonds", "badam"},
    "pista": {"pistachio", "pistachios", "pista"},
    "akhrot": {"walnut", "walnuts", "akhrot"},
    "chironji": {"charoli", "chironji"},
    "chia": {"chia"},
    # dals / pulses
    "moong": {"moong", "green gram"},
    "masoor": {"masoor", "red lentil", "red lentils"},
    "urad": {"urad", "black gram"},
    "chana": {"chana", "bengal gram", "chickpea", "chickpeas"},
    "toor": {"toor", "arhar", "pigeon pea", "pigeon peas"},
    "rajma": {"rajma", "kidney bean", "kidney beans"},
    # beverages
    "chai": {"tea", "chai"},
    "tea": {"tea", "chai"},
    "coffee": {"coffee", "cold brew"},
    "beverages": {"beverages", "tea", "coffee"},
    # spices (common)
    "haldi": {"turmeric", "haldi"},
    "dhania": {"coriander", "dhania"},
    "mirchi": {"chilli", "chili", "mirchi"},
}

# Categories we care about for quick gating (lowercased)
CATEGORY_ALIASES: Dict[str, Set[str]] = {
    "pulses": {"pulses", "dals", "lentils"},
    "spices": {"spices", "spice"},
    "dry fruits": {"dry fruits", "nuts", "seeds"},
    "tea, coffee and beverages": {"tea, coffee and beverages", "beverages", "tea", "coffee"},
}

def is_smalltalk(msg: str) -> bool:
    m = msg.lower().strip()
    return bool(m and (GREETING_RE.search(m) or SMALLTALK_RE.search(m)))

def expand_query_with_synonyms(q: str) -> str:
    """
    Expand Hinglish/Hindi tokens to English (and vice-versa) to help the retriever.
    Example: 'kaju hai?' -> 'kaju cashew cashews'
             'chai' -> 'chai tea'
    """
    toks = _tokens(q)
    expanded: List[str] = []
    added: Set[str] = set()
    for t in toks:
        expanded.append(t)
        if t in SYNONYMS:
            for s in SYNONYMS[t]:
                if s not in added:
                    expanded.append(s)
                    added.add(s)
        else:
            # if token is English and appears in any synonym set, add its group too
            for group in SYNONYMS.values():
                if t in group:
                    for s in group:
                        if s not in added:
                            expanded.append(s)
                            added.add(s)
                    break
    return " ".join(expanded)


# --------------------------- Strict filter ---------------------------
def _strict_filter_hits(hits: List[Dict[str, Any]], user_msg: str) -> List[Dict[str, Any]]:
    """
    Keep hits whose title/category look relevant to the (expanded) user query.
    - Accept if title tokens intersect with query tokens or any mapped synonyms.
    - If category is present, accept when it matches a known alias of the query family.
    - Optionally enforce MIN_SIM if hit contains "sim".
    """
    q_expanded = expand_query_with_synonyms(user_msg)
    q_tokens = set(_tokens(q_expanded))

    # detect probable family from tokens (nuts, pulses, beverages, spices)
    family_hint = None
    for fam, aliases in CATEGORY_ALIASES.items():
        if q_tokens & aliases:
            family_hint = fam
            break

    filtered = []
    for h in hits:
        if MIN_SIM is not None and (h.get("sim") or 0.0) < MIN_SIM:
            continue

        title = (h.get("title") or "")
        title_tokens = set(_tokens(title))
        category = (h.get("category") or "").lower()

        title_match = bool(q_tokens & title_tokens)

        category_match = False
        if category:
            cat_norm = category.strip().lower()
            if family_hint and family_hint in CATEGORY_ALIASES:
                category_match = cat_norm in CATEGORY_ALIASES[family_hint]
            else:
                # loose category pass: if cat token overlaps query tokens
                cat_tokens = set(_tokens(cat_norm))
                category_match = bool(q_tokens & cat_tokens)

        # decision: accept if title looks relevant OR (title mildly relevant + category aligns)
        if title_match or category_match:
            filtered.append(h)

    return filtered


# --------------------------- Context builder ---------------------------
def _build_context_block(results: List[Dict[str, Any]]) -> str:
    lines = []
    for i, r in enumerate(results, start=1):
        title = r.get("title") or ""
        price = r.get("price_inr")
        wt = r.get("weight") or {}
        pack = f'{wt.get("value")} {wt.get("unit")}' if wt.get("value") and wt.get("unit") else ""
        link = r.get("link") or ""
        section = r.get("section") or ""
        text = (r.get("text") or "").strip()
        if len(text) > 400:
            text = text[:400].rstrip() + "..."
        price_str = f"₹{price}" if price is not None else "₹—"
        pack_str = f" | Pack: {pack}" if pack else ""
        lines.append(
            f"[{i}] {title} | {price_str}{pack_str}\n"
            f"    Link: {link}\n"
            f"    Section: {section}\n"
            f"    Snippet: {text}"
        )
    return "\n".join(lines)


@router.post("/tata/chat", response_model=ChatOut)
def tata_chat(body: ChatIn):
    """
    Strict, grounded Tata Sampann assistant with Hinglish/Hindi synonym expansion.
    - Smalltalk → greeting only (no retrieval)
    - Product queries → query expansion → retrieve → strict post-filter → LLM
    - No strong hits → short fallback, used_results=[]
    """
    system_text = render_system_content({
        "brand": "Tata Sampann",
        "today": date.today().isoformat(),
    }) or "You are a grounded product assistant. Answer only from provided context."

    user_msg = (body.message or "").strip()
    if not user_msg or is_smalltalk(user_msg):
        return ChatOut(
            reply="Hello! How can I assist you with Tata Sampann products today?",
            used_results=[],
            meta={"model": MODEL, "intent": "non_product"}
        )

    parsed = extract_filters(user_msg)
    expanded_q = expand_query_with_synonyms(parsed.get("query") or user_msg)

    try:
        results_or_explain = core_search(
            q=expanded_q,
            k=K,
            category=parsed.get("category"),
            max_price=parsed.get("max_price"),
            weight_value=parsed.get("weight_value"),
            weight_unit=parsed.get("weight_unit"),
            distinct_by_sku=DISTINCT_BY_SKU,
            sort=SORT,
            explain=False,
            ranker=RANKER,
            ce_model=CE_MODEL,
            ce_k=CE_K,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")

    hits = results_or_explain if isinstance(results_or_explain, list) else results_or_explain.get("results", []) or []

    # Strict post-filter using expanded tokens (handles 'kaju', 'chai', etc.)
    strict_hits = _strict_filter_hits(hits, user_msg)

    if not strict_hits:
        return ChatOut(
            reply=("I'd be happy to help! For accurate pricing, please let me know the product and pack size - for example, 'Sugar 5 kg' or 'Rice 10 kg'."),
            used_results=[],
            meta={"model": MODEL, "intent": "product", "reason": "no_strong_hits", "retrieved": len(hits)}
        )

    context = _build_context_block(strict_hits)
    user_turn = (
        "User question:\n"
        f"{user_msg}\n\n"
        "Context (use for answering; do not fabricate; cite with [#] by index when referring to products):\n"
        f"{context}\n\n"
        "Instructions:\n"
        "- Answer only from the context above.\n"
        "- If the answer is not present, say you don't have enough information.\n"
        "- When listing products, include name, pack size, price, and link; add [#] citation.\n"
        "- Be concise and helpful."
    )

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            temperature=TEMPERATURE,
            messages=[{"role": "system", "content": system_text},
                      {"role": "user", "content": user_turn}],
        )
        reply = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {e}")

    return ChatOut(
        reply=reply,
        used_results=strict_hits,
        meta={
            "model": MODEL,
            "ranker": RANKER,
            "sort": SORT,
            "k": K,
            "prompt_path": os.getenv("PROMPT_PATH"),
            "intent": "product",
            "retrieved": len(hits),
            "used": len(strict_hits),
            "expanded_query": expanded_q,
        },
    )
