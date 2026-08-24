import sys
from pathlib import Path
from types import SimpleNamespace

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


def test_maritime_one_command_exposes_only_research_decisions(monkeypatch, tmp_path: Path):
    captured = []

    def fake_maritime(request, _root):
        captured.append(request)
        return SimpleNamespace(
            build_id="maritime-ux",
            output=tmp_path / "maritime-ux",
            qgis_project=tmp_path / "maritime-ux" / "project" / "workspace.qgz",
            elapsed_seconds=12.5,
        )

    monkeypatch.setattr(cli, "execute_maritime_build", fake_maritime)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mgrb",
            "build",
            "taiwan-east",
            "--from",
            "2024-01-01",
            "--to",
            "2026-08-23",
            "--actors",
            "plan,ccg,research,fishing",
            "--output",
            "paper,qgis,media",
            "--output-root",
            str(tmp_path),
            "--output-name",
            "maritime-ux",
        ],
    )
    cli.main()
    assert len(captured) == 1
    request = captured[0]
    assert request.area == "taiwan-east"
    assert request.output_root == tmp_path
    assert request.actors == ("plan", "ccg", "research", "fishing")
    assert request.local_inputs == ()
