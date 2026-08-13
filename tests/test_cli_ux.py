import sys
from pathlib import Path

from mgrb import cli, workflow


def test_one_command_build_orchestrates_acquisition_and_qgis(monkeypatch, tmp_path: Path):
    commands = []

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))

    monkeypatch.setattr(workflow.subprocess, "run", fake_run)
    original_find_spec = workflow.importlib.util.find_spec
    monkeypatch.setattr(
        workflow.importlib.util,
        "find_spec",
        lambda name: object() if name == "qgis.core" else original_find_spec(name),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mgrb",
            "build",
            "taiwan_east_south",
            "--profile",
            "local",
            "--theme",
            "canonical",
            "--output-name",
            "ux-test",
            "--output",
            str(tmp_path),
        ],
    )
    cli.main()
    assert len(commands) == 2
    assert "prepare_owner_review.py" in commands[0][0][1]
    assert commands[0][0][-2:] == ["--output-name", "ux-test"]
    assert "build_qgis_projects.py" in commands[1][0][1]
    assert "--build-id" in commands[1][0]
