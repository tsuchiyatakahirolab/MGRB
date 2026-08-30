from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from mgrb.infrastructure import WorldPortIndexAdapter, import_infrastructure


def test_world_port_index_schema_and_geometry(tmp_path: Path) -> None:
    path = tmp_path / "UpdatedPub150.csv"
    pd.DataFrame(
        [
            {
                "World Port Index Number": 1234,
                "Main Port Name": "Test Port",
                "Country Code": "TW",
                "Latitude": 25.0,
                "Longitude": 121.5,
            }
        ]
    ).to_csv(path, index=False)
    frame = WorldPortIndexAdapter().read(path)
    assert len(frame) == 1
    assert frame.iloc[0]["port_name"] == "Test Port"
    assert frame.crs.to_epsg() == 4326


def test_byo_cable_import_preserves_lineage_without_fabrication(tmp_path: Path) -> None:
    path = tmp_path / "cable.geojson"
    gpd.GeoDataFrame(
        {"name": ["Research-authorized route"]},
        geometry=[LineString([(120, 20), (121, 21)])],
        crs=4326,
    ).to_file(path, driver="GeoJSON")
    frame, metadata = import_infrastructure(
        path,
        layer_kind="SUBMARINE_CABLE",
        source_class="BYO_LICENSED",
        source_name="Owner source",
        license_text="OWNER_REVIEWED",
        attribution="Owner source",
        redistribution="NOT_ALLOWED",
    )
    assert len(frame) == 1
    assert metadata.source_sha256
    assert frame.iloc[0]["redistribution"] == "NOT_ALLOWED"


def test_reference_only_infrastructure_is_not_importable(tmp_path: Path) -> None:
    path = tmp_path / "landing.geojson"
    gpd.GeoDataFrame({"name": ["x"]}, geometry=[Point(120, 20)], crs=4326).to_file(
        path, driver="GeoJSON"
    )
    with pytest.raises(ValueError, match="REFERENCE_ONLY"):
        import_infrastructure(
            path,
            layer_kind="CABLE_LANDING_POINT",
            source_class="REFERENCE_ONLY",
            source_name="Proprietary reference",
            license_text="PROPRIETARY",
            attribution="Provider",
            redistribution="NOT_ALLOWED",
        )
