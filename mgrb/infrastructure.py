from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from .provenance import sha256

WPI_DOWNLOAD_URL = (
    "https://msi.nga.mil/api/publications/download?"
    "key=16920959/SFH00000/UpdatedPub150.csv&type=view"
)


@dataclass(frozen=True)
class InfrastructureImport:
    layer_kind: str
    source_class: str
    source_sha256: str
    feature_count: int
    geometry_types: tuple[str, ...]
    attribution: str
    license: str
    redistribution: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class WorldPortIndexAdapter:
    source_id = "nga_world_port_index"
    dataset_url = "https://msi.nga.mil/Publications/WPI"
    download_url = WPI_DOWNLOAD_URL

    def acquire(self, cache_dir: Path) -> Path:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / "UpdatedPub150.csv"
        if path.exists() and path.stat().st_size > 0:
            return path
        request = urllib.request.Request(
            self.download_url, headers={"User-Agent": "MGRB/1.1 public-data-build"}
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = response.read()
        if len(payload) < 1000:
            raise RuntimeError("NGA World Port Index download is unexpectedly small")
        path.write_bytes(payload)
        return path

    def read(self, path: Path) -> gpd.GeoDataFrame:
        frame = pd.read_csv(path, low_memory=False)
        required = {"World Port Index Number", "Main Port Name", "Latitude", "Longitude"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"World Port Index schema changed; missing {sorted(missing)}")
        latitude = pd.to_numeric(frame["Latitude"], errors="coerce")
        longitude = pd.to_numeric(frame["Longitude"], errors="coerce")
        valid = latitude.between(-90, 90) & longitude.between(-180, 180)
        frame = frame.loc[valid].copy()
        frame["port_id"] = frame["World Port Index Number"].astype("Int64").astype(str)
        frame["port_name"] = frame["Main Port Name"].fillna("").astype(str)
        frame["country"] = frame.get("Country Code", "").fillna("").astype(str)
        frame["source_id"] = self.source_id
        frame["source_url"] = self.dataset_url
        frame["retrieved_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        keep = ["port_id", "port_name", "country", "source_id", "source_url", "retrieved_utc"]
        return gpd.GeoDataFrame(
            frame[keep],
            geometry=gpd.points_from_xy(longitude.loc[valid], latitude.loc[valid]),
            crs=4326,
        )

    def source_record(self, path: Path, feature_count: int) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "provider": "US National Geospatial-Intelligence Agency",
            "dataset": "World Port Index, Pub. 150",
            "version_or_date": "provider-current; retrieval timestamp recorded",
            "original_url": self.dataset_url,
            "provider_download_url": self.download_url,
            "license": "United States government publication; provider notices retained",
            "allowed_use": "normalized public port context with source caveat",
            "attribution_required": True,
            "redistribution_allowed": "REVIEW_PROVIDER_NOTICES",
            "commercial_use_known": False,
            "source_sha256": sha256(path),
            "normalized_feature_count": feature_count,
            "availability": "AVAILABLE",
            "quality_caveat": "General reference only; not a substitute for current charts",
        }


def import_infrastructure(
    path: Path,
    *,
    layer_kind: str,
    source_class: str,
    source_name: str,
    license_text: str,
    attribution: str,
    redistribution: str,
) -> tuple[gpd.GeoDataFrame, InfrastructureImport]:
    if layer_kind not in {"PORT", "CABLE_LANDING_POINT", "SUBMARINE_CABLE", "OTHER"}:
        raise ValueError(f"Unsupported infrastructure layer kind: {layer_kind}")
    if source_class not in {"OPEN", "REFERENCE_ONLY", "BYO_LICENSED"}:
        raise ValueError(f"Unsupported infrastructure source class: {source_class}")
    if source_class == "REFERENCE_ONLY":
        raise ValueError("REFERENCE_ONLY data cannot be imported or redistributed")
    frame = gpd.read_file(path)
    if frame.crs is None:
        raise ValueError("Infrastructure layer has no CRS")
    frame = frame.to_crs(4326)
    geometry_types = tuple(sorted(frame.geometry.dropna().geom_type.unique()))
    allowed = (
        {"Point", "MultiPoint"}
        if layer_kind in {"PORT", "CABLE_LANDING_POINT"}
        else {"LineString", "MultiLineString"}
        if layer_kind == "SUBMARINE_CABLE"
        else {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}
    )
    if not set(geometry_types) <= allowed:
        raise ValueError(f"Geometry {geometry_types} is not valid for {layer_kind}")
    result = frame.copy()
    result["infrastructure_kind"] = layer_kind
    result["source_class"] = source_class
    result["source_name"] = source_name
    result["license"] = license_text
    result["attribution"] = attribution
    result["redistribution"] = redistribution
    result["source_sha256"] = sha256(path)
    metadata = InfrastructureImport(
        layer_kind=layer_kind,
        source_class=source_class,
        source_sha256=sha256(path),
        feature_count=len(result),
        geometry_types=geometry_types,
        attribution=attribution,
        license=license_text,
        redistribution=redistribution,
    )
    return result, metadata


def write_infrastructure_sidecar(path: Path, metadata: InfrastructureImport) -> Path:
    sidecar = path.with_name(path.name + ".mgrb-infrastructure.json")
    sidecar.write_text(
        json.dumps(metadata.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return sidecar
