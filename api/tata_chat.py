# api/tata_chat.py
from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

from api.tata_search import search as core_search
from api.prompt_loader import render_system_content
from api.query_prep import extract_filters

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

MODEL = "gpt-4.1-nano"
TEMPERATURE = 0.1
K = 8
RANKER = "cross_encoder"
SORT = "relevance"
DISTINCT_BY_SKU = True
CE_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
CE_K = 40
MIN_SIM: Optional[float] = None

class ChatIn(BaseModel):
    message: str = Field(..., description="User message/question")
    class Config:
        extra = "ignore"

class ChatOut(BaseModel):
    reply: str
    used_results: List[Dict[str, Any]]
    meta: Dict[str, Any]

GREETING_RE = re.compile(r"\b(hi|hey|hello|yo|namaste|good (morning|afternoon|evening))\b", re.I)
SMALLTALK_RE = re.compile(r"\b(how are you|what'?s up|thanks|thank you|help)\b", re.I)

def _tokens(s: str) -> List[str]:
    s = re.sub(r"[^\w\u0900-\u097F]+", " ", s.lower())
    return [t for t in s.split() if t]

SYNONYMS: Dict[str, Set[str]] = {
    "kaju": {"cashew", "cashews", "kaju"},
    "badam": {"almond", "almonds", "badam"},
    "pista": {"pistachio", "pistachios", "pista"},
    "akhrot": {"walnut", "walnuts", "akhrot"},
    "chironji": {"charoli", "chironji"},
    "chia": {"chia", "chia seeds"},
    "chia seeds": {"chia", "chia seeds"},
    "dates": {"dates", "khajoor"},
    "kalmi": {"kalmi", "kalmi dates", "dates", "khajoor"},
    "kalmi dates": {"kalmi", "kalmi dates", "dates", "khajoor"},
    "moong": {"moong", "green gram"},
    "masoor": {"masoor", "red lentil", "red lentils"},
    "urad": {"urad", "black gram"},
    "chana": {"chana", "bengal gram", "chickpea", "chickpeas"},
    "toor": {"toor", "arhar", "pigeon pea", "pigeon peas"},
    "rajma": {"rajma", "kidney bean", "kidney beans"},
    "chai": {"tea", "chai"},
    "tea": {"tea", "chai"},
    "coffee": {"coffee", "cold brew"},
    "beverages": {"beverages", "tea", "coffee"},
    "haldi": {"turmeric", "haldi"},
    "dhania": {"coriander", "dhania"},
    "mirchi": {"chilli", "chili", "mirchi"},
}

CATEGORY_ALIASES: Dict[str, Set[str]] = {
    "pulses": {"pulses", "dals", "lentils"},
    "spices": {"spices", "spice"},
    "dry fruits": {"dry fruits", "nuts", "seeds", "dates"},
    "tea, coffee and beverages": {"tea, coffee and beverages", "beverages", "tea", "coffee"},
}

BROWSE_RE = re.compile(
    r"\b(list( all)?|show( me)?|browse|catalogue|catalog|all products?|what (do you|you) have|menu|range|entire (list|range))\b",
    re.I,
)
COMPARE_RE = re.compile(r"\b(compare|vs|versus)\b", re.I)

def is_smalltalk(msg: str) -> bool:
    m = msg.lower().strip()
    return bool(m and (GREETING_RE.search(m) or SMALLTALK_RE.search(m)))

def is_browse_intent(msg: str) -> bool:
    m = (msg or "").strip().lower()
    return bool(m and BROWSE_RE.search(m))

def is_compare_intent(msg: str) -> bool:
    return bool(COMPARE_RE.search(msg or ""))

def expand_query_with_synonyms(q: str) -> str:
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
            for group in SYNONYMS.values():
                if t in group:
                    for s in group:
                        if s not in added:
                            expanded.append(s)
                            added.add(s)
                    break
    return " ".join(expanded)

GENERIC_TOKENS: Set[str] = {
    "tata", "sampann", "premium", "superfood", "healthy", "pack", "pure",
    "natural", "seed", "seeds", "nut", "nuts", "dry", "fruits", "dates",
    "product", "food", "brand", "range"
}

def _required_tokens_for_target(target: str) -> Set[str]:
    """
    Extract distinctive tokens from the user's target.
    We require at least one of these to appear in the product title.
    Example:
      'chia seeds'   -> {'chia'}
      'kalmi dates'  -> {'kalmi'}  (avoid matching generic 'dates' only)
    """
    toks = set(_tokens(target))
    toks = {t for t in toks if t not in GENERIC_TOKENS and len(t) >= 3}
    if toks:
        return toks
    # Fallback: if everything was generic, keep the longest token
    all_toks = _tokens(target)
    return {max(all_toks, key=len)} if all_toks else set()

def _strict_filter_hits(hits: List[Dict[str, Any]], user_msg: str, *, relax: bool = False) -> List[Dict[str, Any]]:
    if relax:
        if MIN_SIM is None:
            return hits
        return [h for h in hits if (h.get("sim") or 0.0) >= MIN_SIM]
    q_expanded = expand_query_with_synonyms(user_msg)
    q_tokens = set(_tokens(q_expanded))
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
                cat_tokens = set(_tokens(cat_norm))
                category_match = bool(q_tokens & cat_tokens)
        if title_match or category_match:
            filtered.append(h)
    return filtered

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

def _split_compare_targets(msg: str) -> List[str]:
    m = (msg or "").lower()
    m = re.sub(r"\bcompare( prices?| price)?( of)?\b", " ", m)
    m = m.replace(" vs ", " and ").replace(" versus ", " and ")
    parts = re.split(r"\band\b|,|&", m)
    parts = [p.strip() for p in parts if p.strip()]
    return parts[:2]

def _unit_price_inr(hit: Dict[str, Any]) -> Optional[float]:
    price = hit.get("price_inr")
    w = hit.get("weight") or {}
    val, unit = w.get("value"), (w.get("unit") or "").lower()
    if price is None or not val or val <= 0:
        return None
    if unit in ("kg", "kilogram", "kilograms"):
        grams = val * 1000
    elif unit in ("g", "gram", "grams"):
        grams = val
    elif unit in ("mg",):
        grams = val / 1000.0
    else:
        return None
    return (price / grams) * 1000.0

def _filter_hits_for_target(hits: List[Dict[str, Any]], target: str) -> List[Dict[str, Any]]:

    req = _required_tokens_for_target(target)
    if not req:
        return hits

    # Build a quick reverse index from synonym token -> set of equivalents
    syn_index: Dict[str, Set[str]] = {}
    for group in SYNONYMS.values():
        for tok in group:
            syn_index.setdefault(tok, set()).update(group)

    def matches_required(name: str) -> bool:
        name_toks = set(_tokens(name))
        for r in req:
            # direct token present
            if r in name_toks:
                return True
            # synonym expansion present
            if r in syn_index and (syn_index[r] & name_toks):
                return True
        return False

    out: List[Dict[str, Any]] = []
    for h in hits:
        if MIN_SIM is not None and (h.get("sim") or 0.0) < MIN_SIM:
            continue
        title = h.get("title") or ""
        if matches_required(title):
            out.append(h)

    return out or hits


def _pick_best_offer(hits: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for h in hits:
        up = _unit_price_inr(h)
        if up is not None:
            scored.append((up, h))
    if scored:
        scored.sort(key=lambda x: x[0])
        return scored[0][1]
    priced = [h for h in hits if h.get("price_inr") is not None]
    if priced:
        return sorted(priced, key=lambda h: h["price_inr"])[0]
    return hits[0] if hits else None

@router.post("/tata/chat", response_model=ChatOut)
def tata_chat(body: ChatIn):
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

    if is_compare_intent(user_msg):
        targets = _split_compare_targets(user_msg)
        if len(targets) < 2:
            return ChatOut(
                reply="Tell me the two products to compare, e.g., 'compare chia seeds vs kalmi dates'.",
                used_results=[],
                meta={"model": MODEL, "intent": "compare", "reason": "missing_targets"}
            )
        used: List[Dict[str, Any]] = []
        bests: List[Dict[str, Any]] = []
        for t in targets:
            q = expand_query_with_synonyms(t)
            try:
                res = core_search(
                    q=q,
                    k=max(K, 12),
                    category=None,
                    max_price=None,
                    weight_value=None,
                    weight_unit=None,
                    distinct_by_sku=DISTINCT_BY_SKU,
                    sort="relevance",
                    explain=False,
                    ranker=RANKER,
                    ce_model=CE_MODEL,
                    ce_k=CE_K,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Search failed: {e}")
            hits = res if isinstance(res, list) else res.get("results", []) or []
            hits_f = _filter_hits_for_target(hits, t)
            if not hits_f:
                continue
            best = _pick_best_offer(hits_f)
            if best:
                used.extend(hits_f[:5])
                bests.append({"target": t, "best": best})
        if len(bests) < 2:
            return ChatOut(
                reply="I couldn't find enough price data to compare. Try specifying product and pack size.",
                used_results=used,
                meta={"model": MODEL, "intent": "compare", "reason": "insufficient_data", "used": len(used)}
            )
        ctx_lines = []
        for i, b in enumerate(bests, start=1):
            r = b["best"]
            title = r.get("title") or b["target"]
            price = r.get("price_inr")
            wt = r.get("weight") or {}
            pack = f'{wt.get("value")} {wt.get("unit")}' if wt.get("value") and wt.get("unit") else ""
            up = _unit_price_inr(r)
            up_str = f"₹{round(up,2)}/kg" if up is not None else "₹—/kg"
            link = r.get("link") or ""
            ctx_lines.append(f"[{i}] {title} | ₹{price if price is not None else '—'} | Pack: {pack} | {up_str}\n    Link: {link}")
        context = "\n".join(ctx_lines)
        prompt = (
            "User asked to compare prices.\n\n"
            f"Items:\n{context}\n\n"
            "Write a concise comparison using only the items above. Mention price, pack, and price per kg if available. "
            "End with a one-line value pick."
        )
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                temperature=0.0,
                messages=[{"role": "system", "content": system_text},
                          {"role": "user", "content": prompt}],
            )
            reply = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM error: {e}")
        return ChatOut(
            reply=reply,
            used_results=used,
            meta={"model": MODEL, "intent": "compare", "used": len(used)}
        )

    browse = is_browse_intent(user_msg)
    parsed = extract_filters(user_msg)
    expanded_q = "*" if browse else expand_query_with_synonyms(parsed.get("query") or user_msg)
    try:
        results_or_explain = core_search(
            q=expanded_q,
            k=K if not browse else max(K, 20),
            category=parsed.get("category"),
            max_price=parsed.get("max_price"),
            weight_value=parsed.get("weight_value"),
            weight_unit=parsed.get("weight_unit"),
            distinct_by_sku=DISTINCT_BY_SKU,
            sort="relevance" if not browse else "popularity",
            explain=False,
            ranker=RANKER,
            ce_model=CE_MODEL,
            ce_k=CE_K,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")
    hits = results_or_explain if isinstance(results_or_explain, list) else results_or_explain.get("results", []) or []
    strict_hits = _strict_filter_hits(hits, user_msg, relax=browse)

    if not strict_hits:
        if browse:
            return ChatOut(
                reply="Product listing is unavailable right now. Try a specific product or category (e.g., 'Chana 1 kg' or 'Spices').",
                used_results=[],
                meta={"model": MODEL, "intent": "browse", "reason": "no_results", "retrieved": len(hits)},
            )
        return ChatOut(
            reply="I'd be happy to help! For accurate pricing, please mention the product and pack size, e.g., 'Sugar 5 kg' or 'Rice 10 kg'.",
            used_results=[],
            meta={"model": MODEL, "intent": "product", "reason": "no_strong_hits", "retrieved": len(hits)}
        )

    context = _build_context_block(strict_hits)
    browse_instr = "- List popular items with name, pack, price, link; include [#] citation. If too many, show 10–20.\n" if browse else ""
    user_turn = (
        "User question:\n"
        f"{user_msg}\n\n"
        "Context (use for answering; do not fabricate; cite with [#] by index when referring to products):\n"
        f"{context}\n\n"
        "Instructions:\n"
        "- Answer only from the context above.\n"
        "- If the answer is not present, say you don't have enough information.\n"
        "- When listing products, include name, pack size, price, and link; add [#] citation.\n"
        f"{browse_instr}"
        "- Be concise and helpful."
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            temperature=TEMPERATURE if not browse else 0.0,
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
            "sort": SORT if not browse else "popularity",
            "k": K if not browse else max(K, 20),
            "prompt_path": os.getenv("PROMPT_PATH"),
            "intent": "browse" if browse else "product",
            "retrieved": len(hits),
            "used": len(strict_hits),
            "expanded_query": expanded_q,
        },
    )
