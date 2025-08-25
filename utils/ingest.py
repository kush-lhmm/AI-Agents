from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
import csv, json, time
from typing import List, Dict, Any
from schema.schema import ProductCard, Passage, norm_pack_size, stable_id, Claim


BASE = ROOT
PERSIST_DIR = BASE / "vector_store_tata"
DATA_DIR = BASE / "data" / "processed"
CSV_PATH = BASE / "assets" / "Tata Sampann Product Details - Sheet1.csv"

COLLECTION = "tata_sampann_passages"
EMB_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PERSIST_DIR.mkdir(parents=True, exist_ok=True)


def load_csv(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def to_float(x):
    try:
        return float(str(x).strip()) if x is not None and str(x).strip() != "" else None
    except Exception:
        return None


def _chunk_text(s: str, size: int = 600, overlap: int = 80) -> list[str]:
    """Simple, dependency-free chunker for long descriptions."""
    s = " ".join((s or "").split())
    if not s:
        return []
    out, i = [], 0
    step = max(1, size - overlap)
    while i < len(s):
        out.append(s[i:i+size])
        i += step
    return out


def build_card(row: Dict, version: str, source: str) -> ProductCard:
    title = (row.get("Product Name") or "").strip()
    if not title:
        raise ValueError("CSV row missing 'Product Name'")

    category = (row.get("Category") or "").strip()
    weight = (row.get("Weight") or "").strip()
    sku_id = stable_id("tata sampann", title, weight)

    # Claims from USP (marketing → unapproved but preserved with provenance)
    usp = (row.get("USP") or "").strip()
    claims = [
        Claim(text=c.strip(), approved=False, source=source)
        for c in usp.split(",") if c.strip()
    ]

    card = ProductCard(
        sku_id=sku_id,
        title=title,
        category=category,
        net_quantity=norm_pack_size(weight),
        variants=[weight] if weight else [],
        claims=claims,
        mrp=to_float(row.get("Price")),
        link=(row.get("Link") or "").strip() or None,
        description=(row.get("Description") or "").strip() or None,
        provenance={
            "source": source,
            "version": version,
            "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )
    return card


def build_passages(card: ProductCard) -> List[Passage]:
    # NOTE: keep only scalars in metadata (lists converted later if needed)
    meta_common: Dict[str, Any] = {
        "sku_id": card.sku_id,
        "title": card.title,
        "category": card.category,
        # lists below will be stringified before upsert
        "dietary_tags": card.dietary_tags,
        "claims": [c.text for c in card.claims if c.approved],
        "version": card.provenance.get("version"),
        "source": card.provenance.get("source"),
        "price_inr": card.mrp,
        "link": card.link,
    }

    qty = card.net_quantity
    qty_txt = (
        f'{qty.get("value")} {qty.get("unit")}'
        if qty.get("value") and qty.get("unit")
        else ""
    )
    traits_txt = ", ".join(sorted({c.text for c in card.claims})) or "—"

    passages: List[Passage] = []

    # Overview
    passages.append(Passage(
        id=f"{card.sku_id}#overview",
        sku_id=card.sku_id,
        text=(
            f"{card.title} {qty_txt} — Category: {card.category}. "
            f"USP: {traits_txt}. MRP ₹{card.mrp if card.mrp is not None else '—'}."
        ),
        metadata=meta_common | {"section_path": "Overview"},
    ))

    # Diet
    passages.append(Passage(
        id=f"{card.sku_id}#diet",
        sku_id=card.sku_id,
        text=f"{card.title}: Dietary suitability — {', '.join(card.dietary_tags) or '—'}.",
        metadata=meta_common | {"section_path": "Diet"},
    ))

    # Description (chunk if long)
    desc = (card.description or "").strip()
    if desc:
        chunks = _chunk_text(desc, size=600, overlap=80) if len(
            desc) > 700 else [desc]
        for idx, chunk in enumerate(chunks, start=1):
            passages.append(Passage(
                id=f"{card.sku_id}#desc-{idx}",
                sku_id=card.sku_id,
                text=f"{card.title}: {chunk}",
                metadata=meta_common | {
                    "section_path": "Description", "desc_part": idx, "desc_total": len(chunks)},
            ))
    else:
        passages.append(Passage(
            id=f"{card.sku_id}#desc-1",
            sku_id=card.sku_id,
            text=f"{card.title}: No description provided.",
            metadata=meta_common | {
                "section_path": "Description", "desc_part": 1, "desc_total": 1},
        ))

    return passages


def validate_card(card: ProductCard) -> List[str]:
    errs = []
    if not card.title:
        errs.append("title missing")
    if not card.category:
        errs.append("category missing")
    nq = card.net_quantity
    if nq.get("unit") and nq.get("unit") not in {"g", "kg", "ml", "l"}:
        errs.append("net_quantity unit invalid")
    return errs


def get_store() -> Chroma:
    embeddings = HuggingFaceEmbeddings(model_name=EMB_MODEL)
    return Chroma(
        collection_name=COLLECTION,
        embedding_function=embeddings,
        persist_directory=str(PERSIST_DIR),
    )


def _sanitize_metadata(md: Dict[str, Any]) -> Dict[str, Any]:
    """Make metadata Chroma-safe (only scalars allowed)."""
    out: Dict[str, Any] = {}
    for k, v in md.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, list):
            # join list as pipe-separated string
            out[k] = "|".join(map(str, v))
        elif isinstance(v, dict):
            # stringify dict
            out[k] = json.dumps(v, ensure_ascii=False)
        else:
            out[k] = str(v)
    return out


def upsert_passages(store: Chroma, passages: List[Passage]):
    """Safe upsert: remove existing IDs, then add with sanitized metadata."""
    ids = [p.id for p in passages]
    try:
        store.delete(ids=ids)  # ok if ids don't exist yet
    except Exception:
        pass

    texts = [p.text for p in passages]
    metadatas = [_sanitize_metadata(p.metadata) for p in passages]

    store.add_texts(texts=texts, metadatas=metadatas, ids=ids)


def write_jsonl(path: Path, items: List[dict]):
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def write_preview(passages: List[Passage], out_path: Path, limit: int = 8):
    """Human-readable preview you can open in any editor."""
    lines = []
    lines.append(
        f"Preview ({min(limit, len(passages))} of {len(passages)} passages)\n")
    for p in passages[:limit]:
        m = p.metadata
        lines.append(
            f"- {p.id} | {m.get('title')} | {m.get('category')} | ₹{m.get('price_inr')} | {m.get('section_path')}\n  {p.text}\n"
        )
    out_path.write_text("\n".join(lines), encoding="utf-8")


def ingest(csv_path: Path):
    version = time.strftime("v%Y%m%d")
    rows = load_csv(csv_path)

    cards: List[ProductCard] = []
    passages: List[Passage] = []
    errors: Dict[str, List[str]] = {}

    for idx, r in enumerate(rows, start=1):
        try:
            card = build_card(r, version=version, source=str(csv_path))
        except Exception as e:
            sid = stable_id("badrow", str(idx))
            errors[sid] = [f"build_card error: {e}"]
            continue

        e = validate_card(card)
        if e:
            errors[card.sku_id] = e
            continue

        cards.append(card)
        passages.extend(build_passages(card))

    write_jsonl(DATA_DIR / "cards.jsonl",    [c.model_dump() for c in cards])
    write_jsonl(DATA_DIR / "passages.jsonl",
                [p.model_dump() for p in passages])
    write_jsonl(
        DATA_DIR / "validation_report.json",
        [{"sku_id": k, "errors": v} for k, v in errors.items()],
    )
    write_preview(passages, DATA_DIR / "preview.txt", limit=8)

    store = get_store()
    upsert_passages(store, passages)

    # terminal summary
    print(
        f"[ingest] file={csv_path.name} rows={len(rows)} cards={len(cards)} passages={len(passages)} errors={len(errors)}")
    if errors:
        for k, v in errors.items():
            print(f" - {k}: {', '.join(v)}")


if __name__ == "__main__":
    if not CSV_PATH.exists():
        raise SystemExit(f"CSV not found at: {CSV_PATH}")
    ingest(CSV_PATH)
    print(f"[ingest] artifacts written under: {DATA_DIR}")
    print(f"[ingest] vector store at: {PERSIST_DIR}")
    print(f"[ingest] preview file: {DATA_DIR / 'preview.txt'}")
