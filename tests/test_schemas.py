import json
from pathlib import Path
from jsonschema import Draft202012Validator


def test_schemas_are_valid():
    root = Path(__file__).resolve().parents[1]
    for name in ["boundary_status.schema.json", "source_manifest.schema.json"]:
        schema = json.loads((root / "schema" / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
