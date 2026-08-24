from __future__ import annotations

import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

import geopandas as gpd
from shapely.geometry import box

from .provenance import sha256


class SourceUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class EvidenceAdapterDescriptor:
    adapter_id: str
    evidence_types: tuple[str, ...]
    mode: str
    licensing: str
    redistribution: str
    notes: str


def evidence_adapter_catalog() -> dict[str, EvidenceAdapterDescriptor]:
    descriptors = (
        EvidenceAdapterDescriptor(
            "global_fishing_watch",
            ("AIS", "SAR_DETECTION", "PORT_RECORD"),
            "IMPORT_OR_AUTHENTICATED_API",
            "Product-specific; pin and record provider terms per build",
            "PRODUCT_SPECIFIC",
            "Supports normalized track, presence, loitering, encounter, gap, port, and SAR imports.",
        ),
        EvidenceAdapterDescriptor(
            "japan_official",
            ("OFFICIAL_OBSERVATION",),
            "PUBLIC_NORMALIZED_IMPORT",
            "Japanese government page terms require review",
            "DERIVED_FACTS_ONLY",
            "Exact, text-relative, and map-derived positions retain different uncertainty.",
        ),
        EvidenceAdapterDescriptor(
            "taiwan_official",
            ("OFFICIAL_OBSERVATION", "PORT_RECORD"),
            "PUBLIC_NORMALIZED_IMPORT",
            "Taiwan government page terms require review",
            "DERIVED_FACTS_ONLY",
            "Official releases and legitimate public port records are normalized locally.",
        ),
        EvidenceAdapterDescriptor(
            "viirs_boat_detection",
            ("VIIRS_BOAT_DETECTION",),
            "IMPORT",
            "Provider-specific",
            "PRODUCT_SPECIFIC",
            "Processed public detections only; no identity is inferred from proximity.",
        ),
        EvidenceAdapterDescriptor(
            "byo",
            ("AIS", "SAR_DETECTION", "OPTICAL_DETECTION", "PORT_RECORD", "USER_SUPPLIED", "LICENSED_EXTERNAL"),
            "LOCAL_IMPORT",
            "User must provide license and allowed-use metadata",
            "EXCLUDED_BY_DEFAULT",
            "CSV, GeoJSON, GeoPackage, and Shapefile are normalized without repository copies.",
        ),
    )
    return {descriptor.adapter_id: descriptor for descriptor in descriptors}


class MarineRegionsWFSAdapter:
    endpoint = "https://geo.vliz.be/geoserver/MarineRegions/wfs"
    layers: ClassVar[dict[str, tuple[str, str]]] = {
        "eez_reference": ("MarineRegions:eez", "marine_regions_eez_v12"),
        "territorial_sea": (
            "MarineRegions:eez_12nm",
            "marine_regions_territorial_sea_v4",
        ),
        "contiguous_zone": (
            "MarineRegions:eez_24nm",
            "marine_regions_contiguous_zone_v4",
        ),
    }

    def fetch(
        self,
        bbox: tuple[float, float, float, float],
        cache_dir: Path,
        *,
        timeout: int = 180,
    ) -> tuple[dict[str, gpd.GeoDataFrame], list[dict[str, object]]]:
        cache_dir.mkdir(parents=True, exist_ok=True)
        output: dict[str, gpd.GeoDataFrame] = {}
        manifests = []
        clip_polygon = box(*bbox)
        for output_name, (type_name, source_id) in self.layers.items():
            parameters = {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": type_name,
                "bbox": ",".join(str(value) for value in (*bbox, "EPSG:4326")),
                "srsName": "EPSG:4326",
                "outputFormat": "application/json",
            }
            url = f"{self.endpoint}?{urllib.parse.urlencode(parameters)}"
            cache_path = cache_dir / f"{output_name}.geojson"
            if not cache_path.exists() or cache_path.stat().st_size == 0:
                partial = cache_path.with_suffix(".geojson.part")
                request = urllib.request.Request(url, headers={"User-Agent": "MGRB/1.0"})
                try:
                    with urllib.request.urlopen(request, timeout=timeout) as response:
                        partial.write_bytes(response.read())
                    partial.replace(cache_path)
                except Exception as exc:
                    partial.unlink(missing_ok=True)
                    raise SourceUnavailable(
                        f"Marine Regions WFS unavailable for {type_name}: {exc}"
                    ) from exc
            frame = gpd.read_file(cache_path)
            if frame.crs is None:
                frame = frame.set_crs(4326)
            else:
                frame = frame.to_crs(4326)
            frame = frame[frame.geometry.intersects(clip_polygon)].copy()
            frame.geometry = frame.geometry.intersection(clip_polygon)
            frame = frame[~frame.geometry.is_empty & frame.geometry.notna()].copy()
            frame["source_id"] = source_id
            frame["boundary_type"] = output_name
            frame["legal_status"] = "provider_reference"
            output[output_name] = frame
            manifests.append(
                {
                    "source_id": source_id,
                    "provider": "Flanders Marine Institute (VLIZ), Marine Regions",
                    "dataset": type_name,
                    "version_or_date": "2023-10-25",
                    "original_url": url,
                    "download_timestamp_utc": datetime.now(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat(),
                    "license": "CC BY 4.0",
                    "allowed_use": "research and redistribution with attribution",
                    "attribution_required": True,
                    "redistribution_allowed": True,
                    "commercial_use_known": True,
                    "spatial_resolution": "provider vector geometry",
                    "temporal_coverage": "version 4/12 released 2023-10-25",
                    "source_sha256": sha256(cache_path),
                    "availability": "AVAILABLE",
                    "transformations": ["WFS bbox selection", "clip to research area"],
                }
            )
        return output, manifests


class WorldBankTrafficDensityAdapter:
    dataset_url = (
        "https://datacatalog.worldbank.org/search/dataset/0037580/"
        "global-shipping-traffic-density"
    )

    def require_cache(self, cache_path: Path | None) -> Path:
        if cache_path is None or not cache_path.exists():
            raise SourceUnavailable(
                "World Bank Global Shipping Traffic Density is available under CC BY 4.0 "
                "but its approximately 510 MB provider archive is not cached. Supply a local "
                "GeoTIFF/archive explicitly; MGRB will not silently substitute another baseline."
            )
        return cache_path
