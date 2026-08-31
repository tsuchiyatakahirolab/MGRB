import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import ValidationError

from mgrb import cli
from mgrb.build_spec import load_build_spec
from mgrb.product import ProductBuildSpec

ROOT = Path(__file__).resolve().parents[1]


def test_spec_resolves_inputs_relative_to_document_and_preserves_kind(tmp_path):
    payload = ProductBuildSpec(
        area="taiwan-east", input_files=("positions.csv",), input_kinds={"positions.csv": "TRACK"}
    ).to_dict()
    path = tmp_path / "build.json"
    path.write_text(json.dumps(payload))
    spec = load_build_spec(path, ROOT)
    expected = str((tmp_path / "positions.csv").resolve())
    assert spec.input_files == (expected,)
    assert spec.input_kinds == {expected: "TRACK"}


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "future"},
        {"mgrb_version": "0.0.0"},
        {"qc": {"track_gap_seconds": 999}},
        {"arbitrary_script": "ignored?"},
        {"start_date": "2026-02-31"},
    ],
)
def test_contract_refuses_silent_semantic_drift(tmp_path, change):
    payload = ProductBuildSpec(area="taiwan-east").to_dict() | change
    path = tmp_path / "build.json"
    path.write_text(json.dumps(payload))
    with pytest.raises((ValueError, ValidationError)):
        load_build_spec(path, ROOT)


def test_duplicate_members_and_oversized_documents_rejected(tmp_path):
    path = tmp_path / "build.json"
    for raw in ('{"area":"taiwan-east","area":"custom"}', " " * (1024 * 1024 + 1)):
        path.write_text(raw)
        with pytest.raises(ValueError):
            load_build_spec(path, ROOT)


def test_cli_validate_spec_never_executes_build(tmp_path, monkeypatch, capsys):
    path = tmp_path / "build.json"
    path.write_text(json.dumps(ProductBuildSpec(area="taiwan-east").to_dict()))
    monkeypatch.setattr("sys.argv", ["mgrb", "build", "--spec", str(path), "--validate-spec"])
    monkeypatch.setattr(cli, "execute_product_build", lambda *a, **kw: pytest.fail("build invoked"))
    cli.main()
    assert json.loads(capsys.readouterr().out)["ok"]


def test_cli_spec_dispatches_to_public_product_builder(tmp_path, monkeypatch, capsys):
    path = tmp_path / "build.json"
    path.write_text(json.dumps(ProductBuildSpec(area="taiwan-east").to_dict()))
    output = tmp_path / "outputs"

    def build(spec, **kwargs):
        assert spec.area == "taiwan-east"
        assert kwargs["output_root"] == output
        assert kwargs["build_id"] == "contract-test"
        return SimpleNamespace(build_id="contract-test", output=output), output / "package.zip"

    monkeypatch.setattr(cli, "execute_product_build", build)
    monkeypatch.setattr(
        "sys.argv",
        [
            "mgrb",
            "build",
            "--spec",
            str(path),
            "--output-root",
            str(output),
            "--output-name",
            "contract-test",
        ],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["build_id"] == "contract-test"


@pytest.mark.parametrize(
    "options", [["--background", "none"], ["--offline"], ["--output", "paper"]]
)
def test_cli_spec_never_silently_ignores_overrides(tmp_path, monkeypatch, options):
    monkeypatch.setattr(
        "sys.argv", ["mgrb", "build", "--spec", str(tmp_path / "not-read.json"), *options]
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
