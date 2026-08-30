from pathlib import Path

from mgrb.layer_registry import LayerRegistry

ROOT = Path(__file__).resolve().parents[1]


def test_registry_records_complete_legal_and_connector_metadata() -> None:
    registry = LayerRegistry.load(ROOT / "config" / "data_layers.yml")
    assert len(registry.records) >= 10
    for record in registry.records.values():
        assert record.provider
        assert record.dataset
        assert record.evidence_context_type
        assert record.geographic_coverage
        assert record.temporal_coverage
        assert record.resolution
        assert record.format
        assert record.acquisition
        assert record.license
        assert record.attribution
        assert record.redistribution
        assert record.commercial_use
        assert record.version_date


def test_cable_sources_are_legally_classified_and_never_fabricated() -> None:
    registry = LayerRegistry.load(ROOT / "config" / "data_layers.yml")
    assert registry.get("osm_submarine_cables").source_class == "OPEN"
    assert registry.get("telegeography_submarine_cable_map").source_class == "REFERENCE_ONLY"
    byo = registry.get("byo_cable_layer")
    assert byo.source_class == "BYO_LICENSED"
    assert "does not fabricate" in (byo.caveat or "")
