import json
import os
import subprocess

import pytest
from pydantic import ValidationError

from engine.assets.batch import BatchPlan, apply_batch, scan_directory
from engine.assets.registry import AssetRegistry
from test_assets import make_glb, provenance


def asset(root, filename, **metadata):
    path = root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    make_glb(path)
    path.with_suffix(".provenance.json").write_text(provenance(**metadata).model_dump_json(), encoding="utf-8")
    return path


def select_all(plan):
    for entry in plan.entries:
        if entry.kind == "candidate":
            entry.selected = True
    return plan


def test_scan_is_stable_unselected_and_sidecar_aware(tmp_path):
    source = tmp_path / "source"
    asset(source, "z/prop.glb")
    asset(source, "a/prop.glb")
    (source / "unsupported.obj").write_text("unsupported")
    first, second = scan_directory(source), scan_directory(source)
    assert first == second
    assert [entry.path for entry in first.entries] == ["a/prop.glb", "unsupported.obj", "z/prop.glb"]
    assert all(not entry.selected for entry in first.entries)
    candidates = [entry for entry in first.entries if entry.kind == "candidate"]
    assert len({entry.id for entry in candidates}) == 2
    assert candidates[0].sha256 == candidates[1].sha256
    assert candidates[0].provenance_sha256
    assert [entry.path for entry in scan_directory(source, recursive=False).entries] == ["unsupported.obj"]


def test_batch_preserves_duplicates_and_is_idempotent(tmp_path):
    source, library = tmp_path / "source", tmp_path / "library"
    asset(source, "a.glb", name="One")
    asset(source, "b.glb", name="Two")
    plan = select_all(scan_directory(source))
    result = apply_batch(plan, source, library)
    assert result["status"] == "succeeded"
    assert result["summary"] == {"selected": 2, "succeeded": 2, "failed": 0, "skipped": 0}
    assert len(list((library / "blobs").glob("*.glb"))) == 1
    assert [entry["version"] for entry in AssetRegistry(library).search()] == [1, 1]
    again = apply_batch(plan, source, library)
    assert again["summary"]["succeeded"] == 2
    assert [entry["version"] for entry in AssetRegistry(library).search()] == [1, 1]
    assert json.loads((library / result["report_file"]).read_text())["status"] == "succeeded"
    assert not list((library / "batches").glob("*/source-*.glb"))


def test_batch_isolates_changed_corrupt_unreviewed_and_missing_sidecars(tmp_path):
    source, library = tmp_path / "source", tmp_path / "library"
    asset(source, "a-valid.glb")
    asset(source, "b-changed.glb")
    asset(source, "c-unreviewed.glb", approval="unreviewed")
    asset(source, "d-no-sidecar.glb").with_suffix(".provenance.json").unlink()
    broken = asset(source, "e-corrupt.glb")
    broken.write_bytes(b"not a GLB")
    plan = select_all(scan_directory(source))
    (source / "b-changed.glb").write_bytes(b"changed after review")
    report = apply_batch(plan, source, library)
    assert report["status"] == "partial"
    assert report["summary"]["succeeded"] == 1
    assert report["summary"]["failed"] == 4
    assert len(AssetRegistry(library).search()) == 1
    assert all(entry.get("error") for entry in report["entries"] if entry["status"] == "failed")
    assert not list((library / "batches").glob("*/source-*.glb"))


def test_provenance_changes_require_rescan(tmp_path):
    source = tmp_path / "source"
    path = asset(source, "prop.glb")
    plan = select_all(scan_directory(source))
    path.with_suffix(".provenance.json").write_text(provenance(name="Changed").model_dump_json())
    report = apply_batch(plan, source, tmp_path / "library")
    assert report["summary"]["failed"] == 1
    assert "provenance" in report["entries"][0]["error"].lower()


def test_no_selection_does_not_create_library(tmp_path):
    source, library = tmp_path / "source", tmp_path / "library"
    asset(source, "prop.glb")
    with pytest.raises(ValueError, match="selected"):
        apply_batch(scan_directory(source), source, library)
    assert not library.exists()


def test_batch_requires_explicit_matching_root_and_disjoint_library(tmp_path):
    source = tmp_path / "source"
    asset(source, "prop.glb")
    plan = select_all(scan_directory(source))
    with pytest.raises(ValueError, match="root"):
        apply_batch(plan, tmp_path, tmp_path / "library")
    with pytest.raises(ValueError, match="inside|overlap"):
        apply_batch(plan, source, source / "library")


@pytest.mark.parametrize("path", ["../outside.glb", "/outside.glb", "C:/outside.glb", "a/../../b.glb", "a\\b.glb"])
def test_plan_rejects_nonportable_or_escaping_paths(tmp_path, path):
    source = tmp_path / "source"
    asset(source, "prop.glb")
    data = scan_directory(source).model_dump()
    data["entries"][0]["path"] = path
    with pytest.raises(ValidationError):
        BatchPlan.model_validate(data)


def test_selected_ids_must_be_unique(tmp_path):
    source = tmp_path / "source"
    asset(source, "a.glb")
    asset(source, "b.glb")
    data = select_all(scan_directory(source)).model_dump()
    data["entries"][1]["id"] = data["entries"][0]["id"]
    with pytest.raises(ValidationError, match="unique"):
        BatchPlan.model_validate(data)


def test_junction_or_symlink_is_never_followed(tmp_path):
    source, outside = tmp_path / "source", tmp_path / "outside"
    asset(source, "real/prop.glb")
    asset(outside, "prop.glb")
    link = source / "linked"
    if os.name == "nt":
        env = os.environ | {"ATLAS_TEST_LINK": str(link), "ATLAS_TEST_TARGET": str(outside)}
        result = subprocess.run(["powershell", "-NoProfile", "-Command",
            "New-Item -ItemType Junction -Path $env:ATLAS_TEST_LINK -Target $env:ATLAS_TEST_TARGET | Out-Null"],
            env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(outside, target_is_directory=True)
    plan = scan_directory(source)
    assert [entry.path for entry in plan.entries] == ["linked", "real/prop.glb"]
    assert plan.entries[0].kind == "blocked"
    forged = plan.model_dump()
    forged["entries"] = [forged["entries"][1]]
    forged["entries"][0].update(path="linked/prop.glb", selected=True)
    report = apply_batch(BatchPlan.model_validate(forged), source, tmp_path / "library")
    assert report["summary"]["failed"] == 1
    assert "Linked" in report["entries"][0]["error"]


def test_interruption_preserves_current_registered_version_and_pending_items(tmp_path, monkeypatch):
    import engine.assets.batch as batch
    source, library = tmp_path / "source", tmp_path / "library"
    asset(source, "a.glb")
    asset(source, "b.glb")
    plan = select_all(scan_directory(source))
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr(batch, "inspect_asset", interrupt)
    with pytest.raises(KeyboardInterrupt):
        apply_batch(plan, source, library, inspect=True)
    path = next((library / "batches").glob("*/report.json"))
    report = json.loads(path.read_text())
    assert report["status"] == "cancelled"
    assert report["entries"][0]["status"] == "cancelled"
    assert report["entries"][0]["version"] == 1
    assert report["entries"][1]["status"] == "pending"
    assert report["summary"]["succeeded"] == 0
    assert not list((library / "batches").glob("*/source-*.glb"))


def test_sidecar_reader_rejects_nonregular_file_descriptor(tmp_path, monkeypatch):
    import stat
    import engine.assets.batch as batch
    source = tmp_path / "source"
    asset(source, "prop.glb")
    with monkeypatch.context() as patch:
        original = os.fstat
        patch.setattr(batch.os, "fstat", lambda fd: os.stat_result((stat.S_IFIFO, *original(fd)[1:])))
        with pytest.raises(ValueError, match="regular"):
            batch._sidecar_bytes(source, "prop.glb")
