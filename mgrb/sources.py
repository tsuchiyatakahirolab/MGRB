from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Region, load_yaml


@dataclass(frozen=True)
class PublicSource:
    source_id: str
    metadata: dict[str, Any]

    def manifest_record(self, layers: list[str], transformations: list[str]) -> dict[str, Any]:
        version = self.metadata.get("version") or self.metadata.get("released")
        return {
            "source_id": self.source_id,
            "provider": self.metadata["provider"],
            "dataset": self.metadata["title"],
            "version_or_date": str(version),
            "url": self.metadata.get("homepage")
            or self.metadata.get("repository")
            or self.metadata.get("download"),
            "doi": self.metadata.get("doi"),
            "licence": self.metadata["licence"],
            "redistribution": self.metadata.get("redistribution"),
            "layers": sorted(layers),
            "transformations": transformations,
        }


class SourceRegistry:
    def __init__(self, sources: dict[str, PublicSource]):
        self.sources = sources

    @classmethod
    def load(cls, path: Path) -> SourceRegistry:
        raw = load_yaml(path).get("sources", {})
        sources: dict[str, PublicSource] = {}
        for source_id, metadata in raw.items():
            missing = {"title", "provider", "licence"} - set(metadata)
            if missing:
                raise ValueError(f"Source {source_id!r} is missing {sorted(missing)}")
            sources[source_id] = PublicSource(source_id, metadata)
        return cls(sources)

    def get(self, source_id: str) -> PublicSource:
        try:
            return self.sources[source_id]
        except KeyError as exc:
            raise ValueError(f"Unknown public source: {source_id}") from exc

    def select(self, region: Region, layer: str, explicit: str | None = None) -> PublicSource:
        if explicit:
            return self.get(explicit)
        preferences = (region.context_sources or {}).get(layer, ())
        if not preferences:
            raise ValueError(f"Region {region.name!r} has no configured source for {layer!r}")
        return self.get(preferences[0])
