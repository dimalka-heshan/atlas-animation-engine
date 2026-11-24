import json
import subprocess
import sys

from test_assets import make_glb, provenance


def cli(*args):
    return subprocess.run([sys.executable, "-m", "apps.cli", *map(str, args)], capture_output=True, text=True)


def test_registry_cli_roundtrip(tmp_path):
    source = make_glb(tmp_path / "prop.glb")
    meta = tmp_path / "provenance.json"
    meta.write_text(provenance().model_dump_json())
    library = tmp_path / "library"
    result = cli("assets", "register", source, "--id", "prop", "--provenance", meta, "--library", library)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["version"] == 1
    result = cli("assets", "search", "--tag", "test", "--library", library)
    assert result.returncode == 0, result.stderr
    assert [entry["id"] for entry in json.loads(result.stdout)] == ["prop"]
    result = cli("assets", "show", "prop", "--version", "1", "--library", library)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["inspection"]["status"] == "pending"


def test_search_missing_library_does_not_create_it(tmp_path):
    library = tmp_path / "absent"
    result = cli("assets", "search", "--library", library)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
    assert not library.exists()


def test_scan_and_reviewed_batch_cli_reports_partial_failure(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    make_glb(source / "approved.glb")
    (source / "approved.provenance.json").write_text(provenance().model_dump_json())
    make_glb(source / "unreviewed.glb")
    (source / "unreviewed.provenance.json").write_text(provenance(approval="unreviewed").model_dump_json())
    plan_path = tmp_path / "plan.json"
    result = cli("assets", "scan", source, "--plan", plan_path)
    assert result.returncode == 0, result.stderr
    plan = json.loads(plan_path.read_text())
    assert all(not entry["selected"] for entry in plan["entries"])
    for entry in plan["entries"]:
        entry["selected"] = True
    plan_path.write_text(json.dumps(plan))
    result = cli("assets", "batch", plan_path, "--root", source, "--library", tmp_path / "library")
    assert result.returncode == 2, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "partial"
    assert report["summary"]["succeeded"] == report["summary"]["failed"] == 1


def test_scan_does_not_overwrite_reviewed_plan(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    plan = tmp_path / "plan.json"
    plan.write_text("already reviewed")
    result = cli("assets", "scan", source, "--plan", plan)
    assert result.returncode == 2
    assert "already exists" in result.stderr
    assert plan.read_text() == "already reviewed"
