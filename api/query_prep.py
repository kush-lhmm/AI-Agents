import re

R_CURRENCY = re.compile(r"(?:₹|\brs\.?\s*|\binr\s*)\s*(\d+(?:\.\d+)?)", re.I)
R_WEIGHT   = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g|l|ml)\b", re.I)

SYNONYMS = {
    r"\bprotein\s*rich\b": "high protein",
    r"\bhigh\s*in\s*protein\b": "high protein",
    r"\bpack\s*size\b": "net weight",
    r"\bnet\s*wt\b": "net weight",
}

def normalize_query(q: str) -> str:
    s = q.strip()
    for pat, repl in SYNONYMS.items():
        s = re.sub(pat, repl, s, flags=re.I)
    # normalize rupee symbol spacing
    s = re.sub(r"₹\s*(\d)", r"₹\1", s)
    return s

def extract_filters(q: str):
    qn = normalize_query(q)

    # price
    max_price = None
    m = R_CURRENCY.search(qn)
    if m:
        try: max_price = float(m.group(1))
        except: pass
    else:
        # look for “under 250”, “<= 250”, “below 250”
        m2 = re.search(r"\b(under|<=|below|less than)\s*(\d+(?:\.\d+)?)\b", qn, re.I)
        if m2:
            try: max_price = float(m2.group(2))
            except: pass

    # weight
    weight_value, weight_unit = None, None
    mw = R_WEIGHT.search(qn)
    if mw:
        weight_value = float(mw.group(1))
        weight_unit  = mw.group(2).lower()

    # category (cheap heuristic; extend as needed)
    category = None
    if re.search(r"\bdry\s*fruits?\b", qn, re.I):
        category = "Dry Fruits"

    # cleaned semantic query (strip explicit filters so embeddings focus on meaning)
    cleaned = qn
    cleaned = R_CURRENCY.sub("", cleaned)
    cleaned = R_WEIGHT.sub("", cleaned)
    cleaned = re.sub(r"\b(under|<=|below|less than)\s*\d+(?:\.\d+)?\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    return {
        "query": cleaned if cleaned else q.strip(),
        "max_price": max_price,
        "weight_value": weight_value,
        "weight_unit": weight_unit,
        "category": category,
    }
