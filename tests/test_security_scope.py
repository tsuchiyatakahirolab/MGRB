import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_upstream_or_private_data_are_tracked():
    tracked = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "data/raw", "data/derived"], text=True
    ).splitlines()
    assert tracked == ["data/derived/.gitkeep", "data/raw/.gitkeep"]


def test_public_tree_has_no_prohibited_workflow_directories():
    prohibited_names = {
        "vessel-data",
        "case-library",
        "anomaly-output",
        "intelligence",
        "private-research",
    }
    directories = {
        path.name.lower()
        for path in ROOT.rglob("*")
        if path.is_dir() and ".git" not in path.parts and ".venv" not in path.parts
    }
    assert prohibited_names.isdisjoint(directories)
