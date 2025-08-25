# utils/json_schema_patch.py
from typing import Any, Dict

def forbid_additional_properties(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively ensure every object schema has additionalProperties: false.
    Modifies a copy to be safe.
    """
    def _walk(node: Any):
        if isinstance(node, dict):
            # If this node is an object schema, enforce additionalProperties: false
            if node.get("type") == "object":
                node.setdefault("properties", {})
                # only set when missing; don't override explicit true/false
                if "additionalProperties" not in node:
                    node["additionalProperties"] = False

            # Recurse through common child keys
            for key in ("properties", "$defs", "definitions"):
                if key in node and isinstance(node[key], dict):
                    for _, child in node[key].items():
                        _walk(child)

            # Also recurse into array item schemas and allOf/oneOf/anyOf
            if "items" in node:
                _walk(node["items"])
            for key in ("allOf", "oneOf", "anyOf"):
                if key in node and isinstance(node[key], list):
                    for child in node[key]:
                        _walk(child)

        elif isinstance(node, list):
            for item in node:
                _walk(item)

    import copy
    patched = copy.deepcopy(schema)
    _walk(patched)
    return patched
