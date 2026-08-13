from pathlib import Path

from mgrb.config import load_regions


def test_regions_load():
    root = Path(__file__).resolve().parents[1]
    regions = load_regions(root / "config/regions.yml")
    assert regions["taiwan_east_south"].longitude_convention == "180"
    assert regions["pacific_360"].longitude_convention == "360"
    assert regions["pacific_360"].bbox == (100.0, -60.0, 300.0, 70.0)
