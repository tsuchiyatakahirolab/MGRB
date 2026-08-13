#!/usr/bin/env python3
"""Acquire pinned public inputs and prepare six owner-review project specifications."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import rasterio
from rasterio.merge import merge
from rasterio.transform import Affine

from mgrb.builder import build_region
from mgrb.config import load_profiles, load_regions, load_yaml
from mgrb.longitude import bbox_360_to_180_parts
from mgrb.sources import SourceRegistry
from mgrb.theme import resolve_theme

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
DERIVED = ROOT / "data/derived"
GEBCO_NCSS = (
    "https://dap.ceda.ac.uk/thredds/ncss/grid/bodc/gebco/global/gebco_2026/"
    "ice_surface_elevation/netcdf/GEBCO_2026.nc"
)
DOWNLOADS = {
    "gshhg_2_3_7": (
        "https://ftp.soest.hawaii.edu/gshhg/gshhg-shp-2.3.7.zip",
        "gshhg-shp-2.3.7.zip",
    ),
}
NATURAL_EARTH_FILES = (
    "110m_physical/ne_110m_land.shp",
    "110m_physical/ne_110m_land.shx",
    "110m_physical/ne_110m_land.dbf",
    "110m_physical/ne_110m_land.prj",
    "10m_cultural/ne_10m_populated_places.shp",
    "10m_cultural/ne_10m_populated_places.shx",
    "10m_cultural/ne_10m_populated_places.dbf",
    "10m_cultural/ne_10m_populated_places.prj",
)
REVIEW_BUILDS = (
    ("taiwan-local-canonical", "taiwan_east_south", "canonical"),
    ("taiwan-local-custom", "taiwan_east_south", "examples/custom-theme.yml"),
    ("east-asia-regional", "east_asia_seas", "canonical"),
    ("west-pacific", "west_pacific", "print-muted"),
    ("pacific-360", "pacific_360", "canonical"),
    ("taiwan-local-grayscale", "taiwan_east_south", "grayscale"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> None:
    if target.exists() and target.stat().st_size:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    print(f"acquire {url} -> {target.relative_to(ROOT)}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "MGRB/1.0 public-data-build"})
    with urllib.request.urlopen(request, timeout=180) as response, partial.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    partial.replace(target)


def extract(archive: Path, target: Path) -> None:
    marker = target / ".complete"
    if marker.exists():
        return
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(target)
    marker.write_text(sha256(archive) + "\n", encoding="utf-8")


def _ncss_url(bbox: tuple[float, float, float, float], stride: int) -> str:
    west, south, east, north = bbox
    query = urllib.parse.urlencode(
        {
            "var": "elevation",
            "north": north,
            "west": west,
            "east": east,
            "south": south,
            "horizStride": stride,
            "accept": "netcdf",
        }
    )
    return f"{GEBCO_NCSS}?{query}"


def _netcdf_to_tiff(source: Path, target: Path, shift: float = 0.0) -> None:
    with rasterio.open(source) as dataset:
        data = dataset.read()
        transform = dataset.transform
        if shift:
            transform = Affine(
                transform.a,
                transform.b,
                transform.c + shift,
                transform.d,
                transform.e,
                transform.f,
            )
        profile = dataset.profile.copy()
        profile.update(
            driver="GTiff",
            transform=transform,
            compress="deflate",
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(target, "w", **profile) as output:
            output.write(data)
            output.update_tags(
                MGRB_SOURCE_ID="gebco_2026",
                MGRB_SOURCE_DOI="10.5285/4f68d5c7-45eb-f999-e063-7086abc036fa",
                MGRB_SOURCE_CITATION=(
                    "GEBCO Bathymetric Compilation Group 2026 (2026), GEBCO_2026 Grid"
                ),
            )


def acquire_gebco(region_name: str, bbox: tuple[float, ...], convention: str, stride: int) -> Path:
    output = RAW / "gebco" / f"{region_name}.tif"
    if output.exists() and output.stat().st_size:
        return output
    work = RAW / "gebco" / "subsets" / region_name
    work.mkdir(parents=True, exist_ok=True)
    parts = bbox_360_to_180_parts(bbox) if convention == "360" else [bbox]
    tiffs = []
    for index, part in enumerate(parts):
        netcdf = work / f"part-{index}.nc"
        download(_ncss_url(part, stride), netcdf)
        tiff = work / f"part-{index}.tif"
        _netcdf_to_tiff(netcdf, tiff, shift=360.0 if convention == "360" and part[0] < 0 else 0.0)
        tiffs.append(tiff)
    if len(tiffs) == 1:
        shutil.copy2(tiffs[0], output)
    else:
        opened = [rasterio.open(path) for path in tiffs]
        try:
            data, transform = merge(opened)
            profile = opened[0].profile.copy()
            profile.update(
                height=data.shape[1],
                width=data.shape[2],
                transform=transform,
                compress="deflate",
                tiled=True,
                blockxsize=256,
                blockysize=256,
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(output, "w", **profile) as dataset:
                dataset.write(data)
                dataset.update_tags(
                    MGRB_SOURCE_ID="gebco_2026",
                    MGRB_LONGITUDE_CONVENTION="0..360",
                    MGRB_SOURCE_DOI="10.5285/4f68d5c7-45eb-f999-e063-7086abc036fa",
                )
        finally:
            for dataset in opened:
                dataset.close()
    return output


def locate_inputs(extracted: Path) -> dict[str, Path]:
    def one(pattern: str) -> Path:
        matches = sorted(extracted.rglob(pattern))
        if not matches:
            raise FileNotFoundError(f"Expected public source file was not found: {pattern}")
        return matches[0]

    return {
        "gshhg_high": one("GSHHS_h_L1.shp"),
        "gshhg_intermediate": one("GSHHS_i_L1.shp"),
        "ne_110m_land": one("ne_110m_land.shp"),
        "ne_labels": one("ne_10m_populated_places.shp"),
    }


def source_manifest(registry: SourceRegistry, region_name: str, land_source: str) -> list[dict]:
    return [
        registry.get("gebco_2026").manifest_record(
            ["bathymetry", "depth_contours"],
            [f"NCSS subset for {region_name}", "profile-specific grid stride"],
        ),
        registry.get(land_source).manifest_record(
            ["land", "coastline"],
            [f"clip to {region_name}", "coastline derived from land polygon boundary"],
        ),
        registry.get("natural_earth_5_1_2").manifest_record(
            ["labels"], [f"clip to {region_name}", "profile rank filtering in QGIS"]
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--region")
    parser.add_argument("--profile")
    parser.add_argument("--theme", default="canonical")
    parser.add_argument("--output-name")
    parser.add_argument("--no-visible-footer", action="store_true")
    args = parser.parse_args()
    if args.force and DERIVED.exists():
        shutil.rmtree(DERIVED)
        DERIVED.mkdir(parents=True)

    acquisitions = []
    extracted = RAW / "extracted"
    for source_id, (url, filename) in DOWNLOADS.items():
        archive = RAW / "downloads" / filename
        download(url, archive)
        extract(archive, extracted / source_id)
        acquisitions.append(
            {
                "source_id": source_id,
                "url": url,
                "path": archive.relative_to(ROOT).as_posix(),
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
            }
        )

    natural_earth_files = []
    natural_earth_root = extracted / "natural_earth_5_1_2"
    for relative in NATURAL_EARTH_FILES:
        url = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/{relative}"
        target = natural_earth_root / relative
        download(url, target)
        natural_earth_files.append(
            {
                "path": target.relative_to(ROOT).as_posix(),
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
        )
    acquisitions.append(
        {
            "source_id": "natural_earth_5_1_2",
            "url": "https://github.com/nvkelso/natural-earth-vector/tree/v5.1.2",
            "files": natural_earth_files,
        }
    )

    paths = locate_inputs(extracted)
    regions = load_regions(ROOT / "config/regions.yml")
    profiles = load_profiles(ROOT / "config/profiles.yml")
    layouts = load_yaml(ROOT / "config/layouts.yml")["layouts"]
    product = load_yaml(ROOT / "config/product.yml")["product"]
    registry = SourceRegistry.load(ROOT / "metadata/sources.yml")
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    builds = REVIEW_BUILDS
    if args.region:
        if args.region not in regions:
            raise SystemExit(f"Unknown region: {args.region}")
        region = regions[args.region]
        profile_name = args.profile or region.profile
        if profile_name != region.profile:
            raise SystemExit(
                f"Region {region.name} canonically requires profile {region.profile}; "
                f"got {profile_name}"
            )
        theme_id = Path(args.theme).stem
        build_id = args.output_name or f"{region.name}-{profile_name}-{theme_id}"
        builds = ((build_id, region.name, args.theme),)

    for region_name in {item[1] for item in builds}:
        region = regions[region_name]
        acquire_gebco(region.name, region.bbox, region.longitude_convention, region.gebco_stride)

    for build_id, region_name, theme_name in builds:
        region = regions[region_name]
        profile = profiles[region.profile]
        if region.profile == "local":
            land = paths["gshhg_high"]
            land_source = "gshhg_2_3_7"
        elif region.profile == "regional":
            land = paths["gshhg_intermediate"]
            land_source = "gshhg_2_3_7"
        else:
            land = paths["ne_110m_land"]
            land_source = "natural_earth_5_1_2"
        theme = resolve_theme(theme_name, ROOT / "config/themes")
        build_region(
            region,
            DERIVED,
            land=land,
            labels=paths["ne_labels"],
            bathymetry=RAW / "gebco" / f"{region.name}.tif",
            bathymetry_width=None,
            bathymetry_prepared_for_region=True,
            output_name=build_id,
            profile=vars(profile),
            layout=layouts[profile.layout],
            theme=theme,
            source_manifest=source_manifest(registry, region_name, land_source),
            repository_root=ROOT,
            build_timestamp_utc=timestamp,
            product=product,
            visible_footer=not args.no_visible_footer,
        )

    manifest = {
        "schema": "mgrb-acquisition-1.0",
        "retrieved_at_utc": timestamp,
        "sources": acquisitions,
        "gebco": {
            "source_id": "gebco_2026",
            "service": GEBCO_NCSS,
            "regions": sorted({item[1] for item in builds}),
        },
    }
    (RAW / "acquisition-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Prepared {len(builds)} project specifications in {DERIVED.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
