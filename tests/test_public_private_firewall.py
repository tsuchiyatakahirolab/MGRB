from pathlib import Path

import pytest

from mgrb.firewall import assert_public_package, audit_public_repository

ROOT = Path(__file__).resolve().parents[1]


def test_public_repository_has_no_private_collector_material() -> None:
    assert audit_public_repository(ROOT) == []


@pytest.mark.parametrize(
    "relative",
    [
        ".local/state.db",
        "browser-profile/Default/Cookies",
        "data/owner-gfw-track.csv",
        "database/gfw_acquisition.sqlite3",
    ],
)
def test_package_firewall_rejects_private_classes(tmp_path: Path, relative: str) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text("private", encoding="utf-8")
    with pytest.raises(RuntimeError, match="PUBLIC_PRIVATE_FIREWALL_BLOCKED"):
        assert_public_package(tmp_path)
