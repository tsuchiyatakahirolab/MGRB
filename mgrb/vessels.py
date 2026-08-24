from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

IDENTIFIER_FIELDS = ("MMSI", "IMO", "callsign", "hull_number")
NAME_FIELDS = ("canonical_name", "name_cn", "name_en")


def normalize_identity_token(value: object) -> str:
    """Normalize multilingual identity tokens without transliterating or guessing."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    return "".join(character for character in text if character.isalnum())


@dataclass(frozen=True)
class EntityResolution:
    entity_id: str | None
    confidence: str
    matched_on: str | None
    ambiguous: bool = False


class VesselRegistry:
    """Small, source-backed vessel/entity registry with deterministic resolution."""

    def __init__(self, records: list[dict[str, Any]]):
        self.records = records
        self.by_id = {record["entity_id"]: record for record in records}
        if len(self.by_id) != len(records):
            raise ValueError("Duplicate entity_id in vessel registry")
        self.identifier_index: dict[tuple[str, str], set[str]] = {}
        self.name_index: dict[str, set[str]] = {}
        for record in records:
            entity_id = str(record["entity_id"])
            for field in IDENTIFIER_FIELDS:
                token = normalize_identity_token(record.get(field))
                if token:
                    self.identifier_index.setdefault((field, token), set()).add(entity_id)
            names = [record.get(field) for field in NAME_FIELDS]
            names.extend(record.get("aliases") or [])
            names.extend(record.get("former_names") or [])
            for name in names:
                token = normalize_identity_token(name)
                if token:
                    self.name_index.setdefault(token, set()).add(entity_id)

    @classmethod
    def load(cls, path: Path, schema_path: Path | None = None) -> VesselRegistry:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        records = payload.get("records", [])
        if not isinstance(records, list):
            raise TypeError("Vessel registry records must be a list")
        if schema_path:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema)
            errors = [
                f"{record.get('entity_id', index)}: {error.message}"
                for index, record in enumerate(records)
                for error in validator.iter_errors(record)
            ]
            if errors:
                raise ValueError("Invalid vessel registry: " + "; ".join(errors))
        return cls(records)

    def get(self, entity_id: str) -> dict[str, Any]:
        try:
            return self.by_id[entity_id]
        except KeyError as exc:
            raise ValueError(f"Unknown vessel entity: {entity_id}") from exc

    def resolve(self, values: Mapping[str, object]) -> EntityResolution:
        asserted_id = str(values.get("entity_id") or "").strip()
        if asserted_id:
            if asserted_id in self.by_id:
                return EntityResolution(asserted_id, "DOCUMENTED", "entity_id")
            return EntityResolution(None, "UNKNOWN", "entity_id")

        for field in IDENTIFIER_FIELDS:
            token = normalize_identity_token(values.get(field))
            if not token:
                continue
            matches = self.identifier_index.get((field, token), set())
            if len(matches) == 1:
                return EntityResolution(next(iter(matches)), "DOCUMENTED", field)
            if len(matches) > 1:
                return EntityResolution(None, "UNKNOWN", field, ambiguous=True)

        for field in ("vessel_name", "canonical_name", "name_cn", "name_en", "alias"):
            token = normalize_identity_token(values.get(field))
            if not token:
                continue
            matches = self.name_index.get(token, set())
            if len(matches) == 1:
                return EntityResolution(next(iter(matches)), "REPORTED", field)
            if len(matches) > 1:
                return EntityResolution(None, "UNKNOWN", field, ambiguous=True)
        return EntityResolution(None, "UNKNOWN", None)

    def subset(self, entity_ids: set[str]) -> list[dict[str, Any]]:
        return [record for record in self.records if record["entity_id"] in entity_ids]


def identifier_is_malformed(field: str, value: object) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    text = str(value or "").strip()
    if not text or text.casefold() in {"nan", "none", "<na>"}:
        return False
    if field == "MMSI":
        return re.fullmatch(r"\d{9}", text) is None
    if field == "IMO":
        return re.fullmatch(r"(?:IMO)?\d{7}", text, flags=re.IGNORECASE) is None
    return False
