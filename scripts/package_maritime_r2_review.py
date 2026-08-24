from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CASES = (
    ("taiwan-east", "MGRB_Taiwan_East_R2_2022_2026", "Taiwan East"),
    ("taiwan-south", "MGRB_Taiwan_South_R2_2022_2026", "Taiwan South"),
    ("rich-public-track", "MGRB_Xue_Long_Arctic_R2_2012", "Xue Long Arctic 2012"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    name = "NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf"
    path = Path("assets/fonts") / name
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


def journal_preview(source: Path, output: Path, width: int = 945) -> None:
    with Image.open(source) as image:
        image = image.convert("RGB")
        height = round(image.height * width / image.width)
        image.resize((width, height), Image.Resampling.LANCZOS).save(
            output, optimize=True
        )


def contact_sheet(root: Path, output: Path) -> None:
    cell_width, image_height, label_height = 760, 950, 58
    canvas = Image.new("RGB", (cell_width * 2, (image_height + label_height) * 3), "#f5f2eb")
    draw = ImageDraw.Draw(canvas)
    font = _font(25, bold=True)
    for row, (_, package_name, title) in enumerate(CASES):
        for column, (filename, profile) in enumerate(
            (("paper_map.png", "PAPER"), ("media_map.png", "MEDIA"))
        ):
            source = root / package_name / "exports" / filename
            with Image.open(source) as image:
                image = image.convert("RGB")
                image.thumbnail((cell_width - 24, image_height - 24), Image.Resampling.LANCZOS)
                left = column * cell_width + (cell_width - image.width) // 2
                top = row * (image_height + label_height) + (image_height - image.height) // 2
                canvas.paste(image, (left, top))
            label = f"{title} — {profile}"
            x = column * cell_width + 18
            y = row * (image_height + label_height) + image_height + 8
            draw.text((x, y), label, fill="#202020", font=font)
    canvas.save(output, optimize=True)


def _csv_count(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return max(0, sum(1 for _ in csv.reader(stream)) - 1)


def _portable_zip(package: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(item for item in package.rglob("*") if item.is_file()):
            info = zipfile.ZipInfo(f"{package.name}/{path.relative_to(package).as_posix()}")
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def _case_summary(root: Path, package_name: str, elapsed: float | None) -> dict:
    package = root / package_name
    build = json.loads((package / "metadata/mgrb-build.json").read_text(encoding="utf-8"))
    qgis = json.loads((package / "metadata/qgis-validation.json").read_text(encoding="utf-8"))
    source = json.loads(
        (package / "metadata/mgrb-source-manifest.json").read_text(encoding="utf-8")
    )
    track_path = package / "derived/track_summary.csv"
    return {
        "build_id": package_name,
        "git_commit": build["git_commit"],
        "region": build["region_profile"],
        "elapsed_seconds": elapsed,
        "observation_count": _csv_count(package / "derived/cleaned_points.csv"),
        "segment_count": _csv_count(track_path),
        "qgis_version": qgis["qgis_version"],
        "layer_count": qgis["layer_count"],
        "layer_groups": qgis["layer_groups"],
        "portable_reopen": qgis["portable_copy_reopen"],
        "relative_paths": qgis["relative_paths"],
        "visual_qa": qgis["visual_qa"],
        "source_ids": [item["source_id"] for item in source["sources"]],
    }


def package_review(root: Path, timings: dict[str, float | None]) -> dict:
    missing = [name for _, name, _ in CASES if not (root / name).is_dir()]
    if missing:
        raise FileNotFoundError(f"Missing review packages: {', '.join(missing)}")
    zip_dir = root / "portable-zips"
    zip_dir.mkdir(exist_ok=True)
    for key, package_name, _ in CASES:
        journal_preview(
            root / package_name / "exports/paper_map.png",
            root / package_name / "exports/journal-width-preview.png",
        )
        _portable_zip(root / package_name, zip_dir / f"{package_name}.zip")
    contact_sheet(root, root / "contact-sheet.png")
    cases = {
        key: _case_summary(root, package_name, timings.get(key))
        for key, package_name, _ in CASES
    }
    summary = {
        "schema": "mgrb-maritime-owner-review-r2-1.0",
        "status": "READY_FOR_OWNER_VISUAL_REVIEW_MARITIME_R2",
        "cases": cases,
        "world_bank": {
            "dataset": "Global Shipping Traffic Density (World Bank Data Catalog 0037580)",
            "license": "CC BY 4.0",
            "provider_archive_sha256": "7d103de52acf355ffc2436909d5d98e9db93f74d6ad237680e5da6d6d24a9248",
            "source_is_optional_analytic_context": True,
        },
        "rich_case": {
            "vessel": "Xue Long",
            "actor": "research/survey vessel",
            "source": "PANGAEA 891818",
            "doi": "10.1594/PANGAEA.891818",
            "temporal_coverage": "2012-07-17 through 2012-09-08",
            "position_count": 3186,
            "method": "documented public underway positions; PUBLIC_TRACK",
            "quality_caveat": "Provider cruise quality flag D; four large-gap flags retained; no behavior events inferred.",
        },
    }
    (root / "review-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    readme = """# MGRB Maritime Owner Visual Review R2

This package contains distinct paper and media compositions for Taiwan East,
Taiwan South, and the public Xue Long 2012 Arctic track. R2 corrects kilometre
scale bars, reduces legend/symbol dominance, adds controlled geographic labels,
keeps raster coverage seamless, and makes the paper/media hierarchy genuinely
different while preserving editable portable QGIS projects.

Public sources are GEBCO 2026, GSHHG/Natural Earth context, Marine Regions where
available, World Bank Global Shipping Traffic Density (CC BY 4.0), the public
official records identified per Taiwan observation, and PANGAEA 891818 (CC BY
3.0) for Xue Long. Exact URLs, versions, checksums, transformations, citation,
and availability are in each machine-readable source/build manifest.

Solid track lines represent dense observed PUBLIC_TRACK positions. Dashed lines
are only inferred connections between sparse observations of the same resolved
entity. Sparse official points are never presented as continuous observed
tracks. The rich case contains 3,186 public positions and 18 observed segments;
four time-gap flags are retained. It does not infer loitering, anomaly, or other
behavior events. World Bank density is contextual, resampled/subset for the map,
and deliberately subordinate to evidence.

Remaining limitations: source records inherit provider caveats; maritime-zone
lines are sourced reference features rather than legal determinations; public
traffic density aggregates 2015–2021 and is not contemporaneous vessel evidence;
owner visual approval is still required before any release.
"""
    (root / "README.md").write_text(readme, encoding="utf-8")
    index_files = sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "review-index.json"
    )
    index = {
        "schema": "mgrb-review-index-1.0",
        "file_count": len(index_files),
        "files": {
            path.relative_to(root).as_posix(): {
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in index_files
        },
    }
    (root / "review-index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("build/maritime-owner-review-r2"))
    parser.add_argument("--east-seconds", type=float)
    parser.add_argument("--south-seconds", type=float)
    parser.add_argument("--rich-seconds", type=float)
    args = parser.parse_args()
    result = package_review(
        args.root.resolve(),
        {
            "taiwan-east": args.east_seconds,
            "taiwan-south": args.south_seconds,
            "rich-public-track": args.rich_seconds,
        },
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
