from pathlib import Path

from mgrb.config import load_profiles, load_regions, load_yaml
from mgrb.sources import SourceRegistry

ROOT = Path(__file__).resolve().parents[1]


def test_source_registry_is_profile_aware_and_not_universal_natural_earth():
    regions = load_regions(ROOT / "config/regions.yml")
    registry = SourceRegistry.load(ROOT / "metadata/sources.yml")
    assert registry.select(regions["taiwan_east_south"], "land").source_id == "gshhg_2_3_7"
    assert registry.select(regions["east_asia_seas"], "coastline").source_id == "gshhg_2_3_7"
    assert registry.select(regions["west_pacific"], "land").source_id == "natural_earth_5_1_2"
    assert {"gebco_2026", "gshhg_2_3_7", "natural_earth_5_1_2"} <= set(registry.sources)


def test_profile_density_decreases_with_scale():
    profiles = load_profiles(ROOT / "config/profiles.yml")
    assert profiles["local"].label_rank_max > profiles["regional"].label_rank_max
    assert profiles["regional"].label_rank_max > profiles["theatre"].label_rank_max
    assert len(profiles["local"].contour_levels_m) > len(profiles["theatre"].contour_levels_m)
    assert (
        profiles["local"].graticule_interval_degrees
        < profiles["regional"].graticule_interval_degrees
    )
    assert (
        profiles["regional"].graticule_interval_degrees
        < profiles["theatre"].graticule_interval_degrees
    )
    assert profiles["local"].scale_bar is True
    assert profiles["theatre"].scale_bar is False
    assert profiles["local"].contour_opacity > profiles["theatre"].contour_opacity
    assert profiles["regional"].bathymetry_opacity > profiles["theatre"].bathymetry_opacity


def test_status_semantics_have_non_color_encodings():
    semantics = load_yaml(ROOT / "config/semantics.yml")
    statuses = semantics["maritime_status"]
    assert set(statuses) == {
        "treaty_delimited",
        "officially_declared",
        "provider_reference",
        "computed_reference",
        "disputed",
        "uncertain",
    }
    assert len({item["dash"] for item in statuses.values()}) >= 4
    assert all(float(item["width_mm"]) > 0 for item in statuses.values())
