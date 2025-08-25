from __future__ import annotations
from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Optional
import hashlib, re

VALID_UNITS = {"g", "kg", "ml", "l"}

def norm_pack_size(raw: str) -> dict:
    if not raw:
        return {"value": None, "unit": None}
    s = raw.strip().lower().replace("litre", "l").replace("liter", "l")
    m = re.match(r"^\s*([\d.]+)\s*([a-zA-Z]+)\s*$", s)
    if not m:
        return {"value": None, "unit": None}
    val = float(m.group(1))
    unit = m.group(2)
    unit = {"ltr": "l", "ltrs": "l", "kgs": "kg", "grams": "g", "gm": "g", "gms": "g"}.get(unit, unit)
    if unit not in VALID_UNITS:
        unit = None
    return {"value": val, "unit": unit}

def stable_id(*parts: str) -> str:
    raw = "|".join([p.strip().lower() for p in parts if p is not None])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16].upper()

class Claim(BaseModel):
    text: str
    approved: bool = False
    source: Optional[str] = None

class ProductCard(BaseModel):
    sku_id: str
    title: str
    brand: str = "Tata Sampann"
    category: str
    net_quantity: Dict[str, Optional[float | str]] = Field(default_factory=dict)
    variants: List[str] = Field(default_factory=list)
    ingredients: List[str] = Field(default_factory=list)   
    allergens: List[str] = Field(default_factory=list)     
    dietary_tags: List[str] = Field(default_factory=list)  
    claims: List[Claim] = Field(default_factory=list)      
    nutrition_per_100g: Dict[str, Optional[float]] = Field(default_factory=dict)
    usage: Optional[str] = None
    storage: Optional[str] = None
    shelf_life: Optional[str] = None
    mrp: Optional[float] = None
    link: Optional[str] = None
    description: Optional[str] = None
    provenance: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def infer_dietary_tags(self):
        # start with whatever was provided
        tags = {t.lower() for t in (self.dietary_tags or [])}

        # build a blob from title/description/claims
        claims_text = " ".join([c.text for c in (self.claims or []) if getattr(c, "text", None)])
        blob = " ".join([
            self.title or "",
            self.description or "",
            claims_text,
        ]).lower()

        if "protein" in blob:
            tags.add("high-protein")
        if "fiber" in blob or "fibre" in blob:
            tags.add("high-fiber")
        if "gluten free" in blob or "gluten-free" in blob:
            tags.add("gluten-free")

        tags.add("vegetarian")

        self.dietary_tags = sorted(tags)
        return self

class Passage(BaseModel):
    id: str
    sku_id: str
    text: str
    metadata: Dict[str, str | float | int | list]
