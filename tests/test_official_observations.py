from pathlib import Path

import pandas as pd
import pytest

from mgrb.official_observations import import_official_observations


def _write(path: Path, method: str, uncertainty: str = "5000") -> None:
    pd.DataFrame(
        [
            {
                "observation_id": "official-1",
                "entity_id": "entity-1",
                "timestamp_start": "2025-02-03T04:05:00Z",
                "latitude": 24.2,
                "longitude": 123.1,
                "actor_type": "OTHER_GOVERNMENT",
                "source_url": "https://example.gov/release/1",
                "source_date": "2025-02-04",
                "observation_method": method,
                "position_uncertainty_m": uncertainty,
                "identity_confidence": "DOCUMENTED",
                "position_confidence": "MEDIUM",
            }
        ]
    ).to_csv(path, index=False)


def test_official_observation_preserves_approximation_and_never_allows_track(
    tmp_path: Path,
) -> None:
    path = tmp_path / "official.csv"
    _write(path, "MAP_DERIVED_POSITION")
    frame, summary = import_official_observations(path, build_id="test")
    assert frame.iloc[0]["source_type"] == "OFFICIAL_OBSERVATION"
    assert bool(frame.iloc[0]["map_derived"])
    assert not bool(frame.iloc[0]["position_exact"])
    assert summary.map_derived_count == 1
    assert not summary.continuous_track_allowed


def test_approximate_official_observation_requires_uncertainty(tmp_path: Path) -> None:
    path = tmp_path / "official.csv"
    _write(path, "APPROXIMATE_POSITION", "")
    with pytest.raises(ValueError, match="position_uncertainty_m"):
        import_official_observations(path, build_id="test")
