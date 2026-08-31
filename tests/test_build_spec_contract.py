import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from mgrb.product import ProductBuildSpec

ROOT = Path(__file__).resolve().parents[1]


def test_public_contract_matches_serialized_build_spec():
    schema = json.loads((ROOT / "schema/product_build.schema.json").read_text())
    spec = ProductBuildSpec(area="south-china-sea", start_date="2026-01-01", end_date="2026-02-01")
    payload = json.loads(json.dumps(spec.to_dict()))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert ProductBuildSpec.from_dict(payload) == spec


def test_contract_rejects_private_recipe_extension_and_bad_dates():
    schema = json.loads((ROOT / "schema/product_build.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert list(validator.iter_errors({"area":"south-china-sea", "server_recipe":"internal"}))
    assert list(validator.iter_errors({"area":"south-china-sea", "start_date":"yesterday"}))
