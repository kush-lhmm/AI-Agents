# scripts/export_schema.py
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import json, pathlib
from models.person_analysis import PersonImageAnalysis

# Generate JSON Schema (draft 2020-12) with $defs
schema_core = PersonImageAnalysis.model_json_schema(ref_template="#/$defs/{model}")

openai_schema = {
    "name": "person_image_analysis",
    "schema": schema_core,
    "strict": True  # helps OpenAI keep to the schema exactly
}

out = pathlib.Path("schema/person.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(openai_schema, indent=2), encoding="utf-8")
print(f"Wrote {out.resolve()}")
