from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import load_yaml

SOURCE_CLASSES = {"OPEN", "REFERENCE_ONLY", "BYO_LICENSED"}
CONNECTOR_STATUSES = {"IMPLEMENTED", "IMPORT_ONLY", "AUDITED", "PLANNED"}
UI_GROUPS = {
    "MARITIME_JURISDICTION",
    "PHYSICAL",
    "TRAFFIC",
    "EVENT_EVIDENCE",
    "INFRASTRUCTURE",
    "RESEARCH_TRACKS",
}


@dataclass(frozen=True)
class LayerRecord:
    layer_id: str
    provider: str
    dataset: str
    url: str | None
    evidence_context_type: str
    geographic_coverage: str
    temporal_coverage: str
    resolution: str
    format: str
    acquisition: str
    license: str
    attribution: str
    redistribution: str
    commercial_use: str
    version_date: str
    connector_status: str
    source_class: str
    ui_group: str
    default_enabled: bool = False
    caveat: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value.isoformat() if isinstance(value, (date, datetime)) else value
            for key, value in asdict(self).items()
        }


class LayerRegistry:
    def __init__(self, records: dict[str, LayerRecord]):
        self.records = records

    @classmethod
    def load(cls, path: Path) -> LayerRegistry:
        payload = load_yaml(path)
        records: dict[str, LayerRecord] = {}
        for layer_id, raw in payload.get("layers", {}).items():
            values = {"layer_id": layer_id, **raw}
            record = LayerRecord(**values)
            if record.source_class not in SOURCE_CLASSES:
                raise ValueError(f"Invalid source_class for {layer_id}: {record.source_class}")
            if record.connector_status not in CONNECTOR_STATUSES:
                raise ValueError(
                    f"Invalid connector_status for {layer_id}: {record.connector_status}"
                )
            if record.ui_group not in UI_GROUPS:
                raise ValueError(f"Invalid ui_group for {layer_id}: {record.ui_group}")
            if record.source_class == "OPEN" and not record.license:
                raise ValueError(f"Open layer {layer_id} requires a license")
            records[layer_id] = record
        if not records:
            raise ValueError("Layer registry is empty")
        return cls(records)

    def get(self, layer_id: str) -> LayerRecord:
        try:
            return self.records[layer_id]
        except KeyError as exc:
            raise ValueError(f"Unknown data/context layer: {layer_id}") from exc

    def catalog(self) -> list[dict[str, Any]]:
        return [self.records[key].to_dict() for key in sorted(self.records)]

    def grouped_catalog(self) -> dict[str, list[dict[str, Any]]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for record in self.catalog():
            groups.setdefault(record["ui_group"], []).append(record)
        return groups
