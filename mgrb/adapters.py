from __future__ import annotations

import hashlib
import io
import json
import shutil
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rasterio
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.merge import merge
from rasterio.transform import Affine
from rasterio.windows import Window, from_bounds
from shapely.geometry import Point, box

from .longitude import bbox_360_to_180_parts
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
            (
                "AIS",
                "SAR_DETECTION",
                "OPTICAL_DETECTION",
                "PORT_RECORD",
                "USER_SUPPLIED",
                "LICENSED_EXTERNAL",
            ),
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
            # Some provider polygons are valid but exceed GDAL's conservative
            # default per-feature GeoJSON size. The response is already pinned
            # and hashed; allow GDAL to read the complete provider feature.
            pyogrio.set_gdal_config_options({"OGR_GEOJSON_MAX_OBJ_SIZE": 0})
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
        "https://datacatalog.worldbank.org/search/dataset/0037580/global-shipping-traffic-density"
    )
    download_url = (
        "https://datacatalogfiles.worldbank.org/ddh-published/0037580/5/"
        "DR0045406/shipdensity_global.zip"
    )
    archive_member = "shipdensity_global.tif"
    archive_sha256 = "7d103de52acf355ffc2436909d5d98e9db93f74d6ad237680e5da6d6d24a9248"

    def acquire(self, cache_dir: Path, *, timeout: int = 900) -> Path:
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / "shipdensity_global.zip"
        if not target.exists() or target.stat().st_size == 0:
            partial = target.with_suffix(".zip.part")
            request = urllib.request.Request(
                self.download_url, headers={"User-Agent": "MGRB/1.0 public-data-build"}
            )
            try:
                with (
                    urllib.request.urlopen(request, timeout=timeout) as response,
                    partial.open("wb") as output,
                ):
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                partial.replace(target)
            except Exception as exc:
                partial.unlink(missing_ok=True)
                raise SourceUnavailable(
                    f"World Bank traffic-density download failed: {exc}"
                ) from exc
        actual = sha256(target)
        if actual != self.archive_sha256:
            raise SourceUnavailable(
                "World Bank traffic-density archive checksum changed; provider update requires "
                f"review (expected {self.archive_sha256}, got {actual})."
            )
        return target

    def require_cache(self, cache_path: Path | None) -> Path:
        if cache_path is None or not cache_path.exists():
            raise SourceUnavailable(
                "World Bank Global Shipping Traffic Density is available under CC BY 4.0 "
                "but its approximately 510 MB provider archive is not cached. Supply a local "
                "GeoTIFF/archive explicitly; MGRB will not silently substitute another baseline."
            )
        return cache_path

    def subset(
        self,
        cache_path: Path,
        bbox: tuple[float, float, float, float],
        output_path: Path,
        *,
        buffer_degrees: float = 0.75,
        max_width: int = 4000,
    ) -> dict[str, object]:
        """Create a compact log-density GeoTIFF without expanding the 9.8 GB source."""
        source = self.require_cache(cache_path).resolve()
        source_hash = sha256(source)
        if source.suffix.casefold() == ".zip":
            raster_source = f"/vsizip/{source.as_posix()}/{self.archive_member}"
        else:
            raster_source = str(source)
        xmin, ymin, xmax, ymax = bbox
        convention_360 = xmax > 180.0
        requested = (
            max(0.0 if convention_360 else -180.0, xmin - buffer_degrees),
            max(-85.0, ymin - buffer_degrees),
            min(360.0 if convention_360 else 180.0, xmax + buffer_degrees),
            min(85.0, ymax + buffer_degrees),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cache_hit = False
        subset_cache: Path | None = None
        if source.suffix.casefold() == ".zip":
            cache_key = hashlib.sha256(
                json.dumps(
                    {
                        "source_sha256": source_hash,
                        "requested": requested,
                        "max_width": max_width,
                        "transform": "log1p-v3-antimeridian-average-resample",
                    },
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()[:24]
            subset_cache = source.parent / "subsets" / f"world-bank-{cache_key}.tif"
            if subset_cache.exists() and subset_cache.stat().st_size:
                shutil.copy2(subset_cache, output_path)
                cache_hit = True
        if cache_hit:
            return {
                "source_path": source,
                "source_sha256": source_hash,
                "subset_sha256": sha256(output_path),
                "subset_bbox": list(requested),
                "transform": "log1p",
                "cache_hit": True,
            }

        parts = bbox_360_to_180_parts(requested) if convention_360 else [requested]
        with rasterio.open(raster_source) as dataset:
            memories: list[MemoryFile] = []
            opened = []
            try:
                windows = []
                for part in parts:
                    window = from_bounds(*part, transform=dataset.transform)
                    window = (
                        window.round_offsets()
                        .round_lengths()
                        .intersection(Window(0, 0, dataset.width, dataset.height))
                    )
                    windows.append((part, window))
                total_width = sum(window.width for _, window in windows)
                scale = max(1.0, total_width / max_width)
                for part, window in windows:
                    out_width = max(1, round(window.width / scale))
                    out_height = max(1, round(window.height / scale))
                    raw = dataset.read(
                        1,
                        window=window,
                        out_shape=(out_height, out_width),
                        resampling=Resampling.average,
                    )
                    valid = np.isfinite(raw)
                    if dataset.nodata is not None:
                        valid &= raw != dataset.nodata
                    valid &= raw >= 0
                    transformed_part = np.full(raw.shape, -9999.0, dtype="float32")
                    transformed_part[valid] = np.log1p(raw[valid].astype("float64")).astype(
                        "float32"
                    )
                    transform = dataset.window_transform(window) * Affine.scale(
                        window.width / out_width, window.height / out_height
                    )
                    if convention_360 and part[0] < 0:
                        transform = Affine(
                            transform.a,
                            transform.b,
                            transform.c + 360.0,
                            transform.d,
                            transform.e,
                            transform.f,
                        )
                    profile = dataset.profile.copy()
                    profile.update(
                        driver="GTiff",
                        count=1,
                        dtype="float32",
                        nodata=-9999.0,
                        width=raw.shape[1],
                        height=raw.shape[0],
                        transform=transform,
                    )
                    memory = MemoryFile()
                    memories.append(memory)
                    part_dataset = memory.open(**profile)
                    part_dataset.write(transformed_part, 1)
                    opened.append(part_dataset)
                if len(opened) == 1:
                    transformed = opened[0].read(1)
                    transform = opened[0].transform
                else:
                    mosaic, transform = merge(opened, nodata=-9999.0)
                    transformed = mosaic[0]
                profile = dataset.profile.copy()
                profile.update(
                    driver="GTiff",
                    count=1,
                    dtype="float32",
                    nodata=-9999.0,
                    width=transformed.shape[1],
                    height=transformed.shape[0],
                    transform=transform,
                    compress="deflate",
                    tiled=True,
                    blockxsize=256,
                    blockysize=256,
                )
                with rasterio.open(output_path, "w", **profile) as output:
                    output.write(transformed, 1)
                    finite = transformed[transformed != -9999.0]
                    quantiles = np.quantile(finite, (0.5, 0.75, 0.9, 0.98)).tolist()
                    output.update_tags(
                        MGRB_SOURCE_ID="world_bank_shipping_density_2021",
                        MGRB_SOURCE_URL=self.dataset_url,
                        MGRB_SOURCE_ARCHIVE_SHA256=source_hash,
                        MGRB_LONGITUDE_CONVENTION="0..360" if convention_360 else "-180..180",
                        MGRB_TRANSFORM="log1p and bbox subset",
                        MGRB_RESAMPLING=(
                            f"average to maximum {max_width} pixels wide"
                            if scale > 1.0
                            else "native source resolution"
                        ),
                        MGRB_DENSITY_QUANTILES=",".join(f"{value:.6f}" for value in quantiles),
                    )
            finally:
                for part_dataset in opened:
                    part_dataset.close()
                for memory in memories:
                    memory.close()
        if subset_cache is not None:
            subset_cache.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output_path, subset_cache)
        return {
            "source_path": source,
            "source_sha256": source_hash,
            "subset_sha256": sha256(output_path),
            "subset_bbox": list(requested),
            "transform": "log1p",
            "cache_hit": False,
            "resampled_to_max_width": max_width,
        }


class PangaeaXueLong2012Adapter:
    source_id = "pangaea_xue_long_2012"
    dataset_url = "https://doi.org/10.1594/PANGAEA.891818"
    download_url = dataset_url + "?format=textfile"
    expected_sha256 = "590789494c690f63a769b6165e094204156d105d0925f99f539b1591448fa879"

    def acquire(self, cache_dir: Path, *, timeout: int = 180) -> Path:
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / "PANGAEA-891818.tsv"
        if not target.exists() or target.stat().st_size == 0:
            partial = target.with_suffix(".tsv.part")
            request = urllib.request.Request(
                self.download_url, headers={"User-Agent": "MGRB/1.0 public-data-build"}
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    partial.write_bytes(response.read())
                partial.replace(target)
            except Exception as exc:
                partial.unlink(missing_ok=True)
                raise SourceUnavailable(f"PANGAEA Xue Long download failed: {exc}") from exc
        actual = sha256(target)
        if actual != self.expected_sha256:
            raise SourceUnavailable(
                "PANGAEA Xue Long source checksum changed; provider update requires review "
                f"(expected {self.expected_sha256}, got {actual})."
            )
        return target

    def read(self, cache_path: Path) -> pd.DataFrame:
        path = self.acquire(cache_path.parent)
        return self.parse(path)

    def parse(self, path: Path) -> pd.DataFrame:
        text = path.read_text(encoding="utf-8")
        marker = "Date/Time\tLongitude\tLatitude\t"
        offset = text.find(marker)
        if offset < 0:
            raise SourceUnavailable("PANGAEA Xue Long table header was not found")
        frame = pd.read_csv(io.StringIO(text[offset:]), sep="\t")
        frame = frame.rename(
            columns={
                "Date/Time": "timestamp_start",
                "Longitude": "longitude",
                "Latitude": "latitude",
            }
        )
        frame["entity_id"] = "research-xue-long"
        frame["vessel_name"] = "Xue Long"
        frame["actor_type"] = "RESEARCH_SURVEY"
        frame["source_type"] = "PUBLIC_TRACK"
        frame["source_name"] = "PANGAEA 891818 Xue Long cruise 76XL20120717"
        frame["source_record_id"] = [f"PANGAEA.891818:{index + 1}" for index in range(len(frame))]
        frame["source_url"] = self.dataset_url
        frame["observation_method"] = "UNDERWAY_CRUISE_TRACK"
        frame["identity_confidence"] = "DOCUMENTED"
        frame["position_confidence"] = "MEDIUM"
        frame["observed_or_inferred"] = "OBSERVED"
        frame["position_uncertainty_m"] = 1000.0
        frame["temporal_uncertainty_s"] = 60.0
        frame["license"] = "CC BY 3.0"
        frame["attribution"] = "Chen, Cai & Ouyang (2018), PANGAEA, doi:10.1594/PANGAEA.891818"
        frame["raw_record_reference"] = self.download_url
        frame["processing_notes"] = (
            "Published underway cruise-track position; provider cruise QC flag D retained as caveat"
        )
        return frame


class ScsdiSouthChinaSeaEventsAdapter:
    """Pinned public SCSDI geolocated-event release from Harvard Dataverse."""

    source_id = "scsdi_dataverse_v1"
    dataset_url = "https://doi.org/10.7910/DVN/GCBWA6"
    download_url = "https://dataverse.harvard.edu/api/access/datafile/6457489"
    expected_sha256 = "5d6f78a8df4336a651816b8c5fa3ce1e85f6bf03d0baf6ae04c7818d413a916f"

    def acquire(self, cache_dir: Path, *, timeout: int = 180) -> Path:
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / "SCSDI-geo-coded-event-data-v1.csv"
        if not target.exists() or target.stat().st_size == 0:
            partial = target.with_suffix(".csv.part")
            request = urllib.request.Request(
                self.download_url, headers={"User-Agent": "MGRB/1.0 public-data-build"}
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    partial.write_bytes(response.read())
                partial.replace(target)
            except Exception as exc:
                partial.unlink(missing_ok=True)
                raise SourceUnavailable(f"SCSDI event-data download failed: {exc}") from exc
        actual = sha256(target)
        if actual != self.expected_sha256:
            raise SourceUnavailable(
                "SCSDI event source checksum changed; provider update requires review "
                f"(expected {self.expected_sha256}, got {actual})."
            )
        return target

    def read(self, cache_path: Path) -> gpd.GeoDataFrame:
        path = self.acquire(cache_path.parent)
        return self.parse(path)

    def parse(self, path: Path) -> gpd.GeoDataFrame:
        frame = pd.read_csv(path, encoding="cp1252")
        required = {
            "event_id",
            "event_date",
            "latitude",
            "longitude",
            "level",
            "radius",
            "source",
        }
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise SourceUnavailable(f"SCSDI event source is missing columns: {missing}")
        latitude = pd.to_numeric(frame["latitude"], errors="coerce")
        longitude = pd.to_numeric(frame["longitude"], errors="coerce")
        event_date = pd.to_datetime(
            frame["event_date"], format="%m/%d/%y", errors="coerce", utc=True
        )
        precision_level = pd.to_numeric(frame["level"], errors="coerce").astype("Int64")
        confidence = precision_level.map(
            lambda value: (
                "HIGH"
                if pd.notna(value) and int(value) == 1
                else "MEDIUM"
                if pd.notna(value) and int(value) <= 4
                else "LOW"
            )
        )
        parsed = gpd.GeoDataFrame(
            {
                "event_id": frame["event_id"].astype(str),
                "entity_id": "",
                "actor_type": "UNKNOWN",
                "event_type": "GEOCODED_DISPUTE_EVENT",
                "start_time": event_date.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_time": event_date.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "confidence": confidence,
                "source_type": "PUBLIC_EVENT",
                "source_name": "SCSDI News-event Data v2.0",
                "source_record_id": frame["event_id"].astype(str),
                "source_url": self.dataset_url,
                "license": "CC0 1.0",
                "attribution": "Sexton & Ravanilla, South China Sea Data Initiative",
                "participant_code": frame.get("event_id_cnty", "").fillna("").astype(str),
                "location_precision_level": precision_level,
                "uncertainty_radius_degrees": pd.to_numeric(frame["radius"], errors="coerce"),
                "location_label": frame.get("location", "").fillna("").astype(str),
                "location_note": frame.get("note_on_location", "").fillna("").astype(str),
                "source_report": frame["source"].fillna("").astype(str),
                "event_notes": frame.get("notes", "").fillna("").astype(str),
                "report_count": pd.to_numeric(frame.get("number_of_report"), errors="coerce"),
                "geometry": [
                    Point(lon, lat) if pd.notna(lon) and pd.notna(lat) else None
                    for lon, lat in zip(longitude, latitude, strict=False)
                ],
            },
            geometry="geometry",
            crs=4326,
        )
        return parsed[parsed.geometry.notna()].copy()
