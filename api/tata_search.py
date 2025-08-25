# api/tata_search.py
from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
import json

from api.query_prep import extract_filters
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# --- optional cross-encoder re-ranking ---
try:
    from sentence_transformers import CrossEncoder
    HAS_CE = True
except Exception:
    HAS_CE = False

# --- paths & config (must match your ingest) ---
BASE_DIR = Path(__file__).resolve().parents[1]
PERSIST_DIR = BASE_DIR / "vector_store_tata"
CARDS_PATH = BASE_DIR / "data" / "processed" / "cards.jsonl"

COLLECTION = "tata_sampann_passages"
# multilingual for Hinglish/Hindi queries
EMB_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

router = APIRouter()

# ---------- load product cards (for post-filtering) ----------
_cards_by_sku: Dict[str, Dict[str, Any]] = {}
_reranker: Optional["CrossEncoder"] = None  # lazy-loaded CE


def _load_cards():
    global _cards_by_sku
    _cards_by_sku = {}
    if CARDS_PATH.exists():
        with CARDS_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                _cards_by_sku[obj["sku_id"]] = obj


_load_cards()


# ---------- vector store ----------
def _get_store() -> Chroma:
    return Chroma(
        collection_name=COLLECTION,
        persist_directory=str(PERSIST_DIR),
        embedding_function=HuggingFaceEmbeddings(model_name=EMB_MODEL),
    )


# ---------- cross-encoder (lazy) ----------
def _get_reranker(model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
    global _reranker
    if _reranker is None:
        if not HAS_CE:
            raise HTTPException(
                500,
                "Cross-encoder not installed. Run: pip install sentence-transformers",
            )
        _reranker = CrossEncoder(model_name)
    return _reranker


# ---------- helpers ----------
def _matches_price(card: Dict[str, Any], max_price: Optional[float]) -> bool:
    if max_price is None:
        return True
    price = card.get("mrp")
    if price is None:
        return False
    try:
        return float(price) <= float(max_price)
    except Exception:
        return False


def _matches_weight(
    card: Dict[str, Any], weight_value: Optional[float], weight_unit: Optional[str]
) -> bool:
    if weight_value is None and weight_unit is None:
        return True
    nq = card.get("net_quantity") or {}
    val = nq.get("value")
    unit = (nq.get("unit") or "").lower()
    if weight_value is not None and val is None:
        return False
    if weight_value is not None and float(val) != float(weight_value):
        return False
    if weight_unit is not None and unit != weight_unit.lower():
        return False
    return True


def _to_hit(doc, score: float, ce: Optional[float] = None) -> Dict[str, Any]:
    md = doc.metadata or {}
    sku = md.get("sku_id")
    card = _cards_by_sku.get(sku, {})
    nq = card.get("net_quantity") or {}
    return {
        "sku_id": sku,
        "title": md.get("title"),
        "category": md.get("category"),
        "price_inr": md.get("price_inr", card.get("mrp")),
        "weight": {"value": nq.get("value"), "unit": nq.get("unit")},
        "link": md.get("link", card.get("link")),
        "section": md.get("section_path"),
        "text": doc.page_content,
        "score": float(score),  # dense distance (lower is better)
        "ce_score": float(ce) if ce is not None else None,  # CE score (higher is better)
    }


def _secondary_sort_key(hit: Dict[str, Any], sort: str) -> Tuple:
    # stable ordering when relevance scores are close
    title = (hit.get("title") or "").lower()
    price = hit.get("price_inr")
    if sort == "price_asc":
        return (price if isinstance(price, (int, float)) else float("inf"), title)
    if sort == "price_desc":
        return (-(price if isinstance(price, (int, float)) else -float("inf")), title)
    if sort == "title_asc":
        return (title,)
    return (title,)


# ---------- API ----------
@router.get("/tata/search")
def search(
    q: str = Query(..., description="Search query"),
    k: int = Query(5, ge=1, le=50, description="Number of results"),
    category: Optional[str] = Query(None, description="Exact category match, e.g. 'Dry Fruits'"),
    max_price: Optional[float] = Query(None, description="Max price in INR"),
    weight_value: Optional[float] = Query(None, description="Exact pack value (e.g., 200)"),
    weight_unit: Optional[str] = Query(None, description="Pack unit (g|kg|ml|l)"),
    distinct_by_sku: bool = Query(True, description="Return at most one result per product"),
    sort: str = Query("relevance", pattern="^(relevance|price_asc|price_desc|title_asc)$"),
    explain: bool = Query(False, description="Return parsed/overridden filters for debugging/UI"),
    # re-ranking controls
    ranker: str = Query("relevance", pattern="^(relevance|cross_encoder)$"),
    ce_model: str = Query("cross-encoder/ms-marco-MiniLM-L-6-v2"),
    ce_k: int = Query(30, ge=5, le=100, description="How many candidates to re-rank with CE"),
):
    # 1) preprocess → inferred filters + cleaned semantic query
    f = extract_filters(q)
    cleaned_q = f["query"]

    # explicit overrides take precedence
    use_category = category if category is not None else f["category"]
    use_max_price = max_price if max_price is not None else f["max_price"]
    use_weight_value = weight_value if weight_value is not None else f["weight_value"]
    use_weight_unit = weight_unit if weight_unit is not None else f["weight_unit"]

    store = _get_store()

    # 2) dense retrieval (+ exact category filter if present)
    chroma_filter = {"category": use_category} if use_category else None
    # fetch more to allow CE + filtering headroom
    raw = store.similarity_search_with_score(
        cleaned_q or q,
        k=max(ce_k, k),
        filter=chroma_filter,
    )

    # 3) early filter by price/weight to shrink CE workload
    candidates = []
    for doc, dist in raw:
        md = doc.metadata or {}
        sku = md.get("sku_id")
        if not sku:
            continue
        card = _cards_by_sku.get(sku)
        if not card:
            continue
        if not _matches_price(card, use_max_price):
            continue
        if not _matches_weight(card, use_weight_value, use_weight_unit):
            continue
        candidates.append((doc, dist))

    # 4) optional cross-encoder re-ranking
    ce_used = False
    scored: List[Dict[str, Any]] = []
    if ranker == "cross_encoder" and candidates:
        reranker = _get_reranker(ce_model)
        pairs = [(cleaned_q or q, d.page_content) for d, _ in candidates]
        ce_scores = reranker.predict(pairs)  # higher = better
        ce_used = True
        for (doc, dist), ce in zip(candidates, ce_scores):
            scored.append(_to_hit(doc, dist, ce=float(ce)))
        # sort by CE desc; then by dense distance asc
        scored.sort(key=lambda h: (-(h["ce_score"] or -1e9), h["score"]))
    else:
        # fallback: relevance-only ranking (distance asc)
        for doc, dist in (candidates if candidates else raw):
            scored.append(_to_hit(doc, dist))
        scored.sort(key=lambda h: (h["score"], h["title"] or ""))

    # 5) group by SKU (keep best passage per product)
    if distinct_by_sku:
        best_by_sku: Dict[str, Dict[str, Any]] = {}
        for h in scored:
            sku = h.get("sku_id")
            if not sku:
                continue
            prev = best_by_sku.get(sku)
            if not prev:
                best_by_sku[sku] = h
                continue
            # choose better by CE if present; else by dense distance
            if ce_used:
                if (h["ce_score"] or -1e9) > (prev["ce_score"] or -1e9):
                    best_by_sku[sku] = h
            else:
                if h["score"] < prev["score"]:
                    best_by_sku[sku] = h
        hits = list(best_by_sku.values())
    else:
        hits = scored

    # 6) final sort
    if sort == "relevance":
        if ce_used:
            hits.sort(
                key=lambda h: (
                    -(h["ce_score"] or -1e9),
                    h["score"],
                )
                + _secondary_sort_key(h, "title_asc")
            )
        else:
            hits.sort(key=lambda h: (h["score"],) + _secondary_sort_key(h, "title_asc"))
    else:
        hits.sort(key=lambda h: _secondary_sort_key(h, sort))

    # 7) truncate
    hits = hits[:k]

    # 8) optional explain block
    if explain:
        return {
            "results": hits,
            "explain": {
                "query_original": q,
                "query_cleaned": cleaned_q,
                "filters_inferred": {
                    "category": f["category"],
                    "max_price": f["max_price"],
                    "weight_value": f["weight_value"],
                    "weight_unit": f["weight_unit"],
                },
                "filters_applied": {
                    "category": use_category,
                    "max_price": use_max_price,
                    "weight_value": use_weight_value,
                    "weight_unit": use_weight_unit,
                },
                "ranker": ranker,
                "ce_model": ce_model if ce_used else None,
                "sort": sort,
                "distinct_by_sku": distinct_by_sku,
            },
        }

    return hits
