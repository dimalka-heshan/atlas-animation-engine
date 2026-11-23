import json
import sqlite3
import struct

import pytest

from engine.assets.glb import inspect_glb
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry


def make_glb(path, document=None, binary=b"\0\0\0\0"):
    document = document or {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}]}
    payload = json.dumps(document).encode()
    payload += b" " * (-len(payload) % 4)
    binary += b"\0" * (-len(binary) % 4)
    chunks = struct.pack("<II", len(payload), 0x4E4F534A) + payload
    if binary:
        chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks)
    return path


def provenance(**updates):
    value = {"name": "Original fixture", "creator": "ATLAS fixture generator",
             "source_url": "urn:atlas:fixture:test", "license_id": "LicenseRef-ATLAS-Generated",
             "license_text": "Original test geometry generated locally; rendering permitted.",
             "approval": "approved", "render_allowed": True, "redistribution_allowed": False,
             "tags": ["test", "prop"], "category": "prop"}
    return Provenance.model_validate(value | updates)


def test_registry_roundtrip_dedup_and_versions(tmp_path):
    source = make_glb(tmp_path / "source.glb")
    registry = AssetRegistry(tmp_path / "library")
    a = registry.register(source, "fixture", provenance())
    assert a["version"] == 1
    assert registry.register(source, "fixture", provenance())["version"] == 1
    b = registry.register(source, "fixture", provenance(description="Revised provenance"))
    assert b["version"] == 2
    assert registry.get("fixture", 1)["provenance"]["description"] == ""
    c = registry.register(source, "alias", provenance(name="Alias"))
    assert a["sha256"] == c["sha256"]
    assert len(list((tmp_path / "library" / "blobs").glob("*.glb"))) == 1
    assert AssetRegistry(tmp_path / "library").get("fixture", 2)["provenance"]["description"] == "Revised provenance"


def test_search_is_deterministic_and_literal(tmp_path):
    source = make_glb(tmp_path / "source.glb")
    registry = AssetRegistry(tmp_path / "library")
    registry.register(source, "zebra", provenance(name="Zebra", tags=["animal"]))
    registry.register(source, "apple", provenance(name="Apple", category="food"))
    registry.register(source, "apple", provenance(name="Red apple", category="food"))
    assert [(r["id"], r["version"]) for r in registry.search()] == [("apple", 2), ("zebra", 1)]
    assert [r["id"] for r in registry.search(tag="animal")] == ["zebra"]
    assert [r["id"] for r in registry.search(query="RED", category="food")] == ["apple"]
    assert registry.search(query="%' OR 1=1 --") == []
    assert registry.search(license_id="CC0-1.0") == []


@pytest.mark.parametrize("updates", [{"approval": "unreviewed"}, {"approval": "rejected"},
    {"render_allowed": False}, {"license_id": "unknown"}, {"restrictions": ["personal use only"]},
    {"license_text": ""}, {"creator": ""}, {"source_url": ""}, {"license_id": "CC-BY-4.0", "attribution": ""}])
def test_unsupported_rights_block_render(updates):
    with pytest.raises(ValueError):
        provenance(**updates).require_render_rights()


def test_registration_does_not_approve_unknown_rights(tmp_path):
    registry = AssetRegistry(tmp_path / "library")
    item = registry.register(make_glb(tmp_path / "source.glb"), "blocked", provenance(approval="unreviewed"))
    assert item["provenance"]["approval"] == "unreviewed"
    with pytest.raises(ValueError, match="approved"):
        registry.resolve("blocked", 1)


def test_hash_tampering_and_missing_version(tmp_path):
    registry = AssetRegistry(tmp_path / "library")
    entry = registry.register(make_glb(tmp_path / "source.glb"), "fixture", provenance())
    with pytest.raises(ValueError, match="version"):
        registry.get("fixture", 99)
    blob = tmp_path / "library" / "blobs" / (entry["sha256"] + ".glb")
    blob.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        registry.resolve("fixture", 1)


def test_migrations_refuse_unknown_schema(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    with sqlite3.connect(root / "assets.sqlite3") as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="schema"):
        AssetRegistry(root)
    with sqlite3.connect(root / "assets.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 99


def test_ids_cannot_choose_storage_paths(tmp_path):
    registry = AssetRegistry(tmp_path / "library")
    with pytest.raises(ValueError):
        registry.register(make_glb(tmp_path / "source.glb"), "../escape", provenance())


def test_glb_parser_reports_embedded_resources(tmp_path):
    report = inspect_glb(make_glb(tmp_path / "source.glb"))
    assert report["format"] == "glb"
    assert report["external_dependencies"] == []
    assert report["animation_count"] == 0


@pytest.mark.parametrize("extra", [
    {"buffers": [{"uri": "../../secret.bin", "byteLength": 4}]},
    {"images": [{"uri": "https://example.com/image.png"}]},
    {"images": [{"uri": "data:image/png;base64,AAAA"}]},
    {"animations": [{"channels": []}]}, {"skins": [{}]},
    {"extensionsUsed": ["KHR_draco_mesh_compression"]},
    {"meshes": [{"primitives": [{"targets": [{}]}]}]},
])
def test_unsupported_glb_rejected_before_blender(tmp_path, extra):
    document = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 4}]} | extra
    with pytest.raises(ValueError):
        inspect_glb(make_glb(tmp_path / "bad.glb", document))


@pytest.mark.parametrize("data", [b"", b"not a glb", struct.pack("<4sII", b"glTF", 2, 999),
    struct.pack("<4sII", b"glTF", 1, 12)])
def test_corrupt_glb_is_actionable(tmp_path, data):
    path = tmp_path / "bad.glb"
    path.write_bytes(data)
    with pytest.raises(ValueError, match="GLB"):
        inspect_glb(path)


@pytest.mark.parametrize("document", [{"asset": []}, {"asset": None}, {"asset": {"version": "2.0"}, "buffers": None},
    {"asset": {"version": "2.0"}, "meshes": [None]}])
def test_malformed_glb_structure_returns_value_error(tmp_path, document):
    with pytest.raises(ValueError, match="GLB"):
        inspect_glb(make_glb(tmp_path / "bad.glb", document))


@pytest.mark.parametrize("url", ["https://", "urn:", "urn:atlas:", "http:whatever"])
def test_approved_provenance_requires_meaningful_source_url(url):
    with pytest.raises(ValueError, match="[Ss]ource"):
        provenance(source_url=url).require_render_rights()


@pytest.mark.parametrize("extra", [
    {"nodes": [{}, {}], "scenes": [{"nodes": [0]}], "scene": 0},
    {"nodes": [{}, {}], "scenes": [{"nodes": [0]}, {"nodes": [1]}], "scene": 0},
    {"nodes": [{"children": [1]}, {"children": [0]}], "scenes": [{"nodes": [0]}]},
    {"nodes": [{"children": [99]}], "scenes": [{"nodes": [0]}]},
    {"textures": [{}]}, {"textures": [{"source": 99}]},
    {"materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 99}}}]},
    {"meshes": [{"primitives": [{"mode": 3}]}]},
])
def test_unsupported_scene_graph_or_missing_texture_reference(tmp_path, extra):
    doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 4}]} | extra
    with pytest.raises(ValueError):
        inspect_glb(make_glb(tmp_path / "bad.glb", doc))


def test_inspection_cannot_certify_different_content(tmp_path):
    registry = AssetRegistry(tmp_path / "library")
    registry.register(make_glb(tmp_path / "source.glb"), "fixture", provenance())
    with pytest.raises(ValueError, match="inspection|[Ii]nspection|hash"):
        registry.set_inspection("fixture", 1, "ready", {"source_sha256": "0" * 64})
    assert registry.get("fixture", 1)["inspection"]["status"] == "pending"


def test_resolve_rechecks_inspection_hash_even_if_database_is_modified(tmp_path):
    registry = AssetRegistry(tmp_path / "library")
    registry.register(make_glb(tmp_path / "source.glb"), "fixture", provenance())
    with sqlite3.connect(registry.path) as db:
        db.execute("INSERT INTO inspections VALUES (?,?,?,?,?)", ("fixture", 1, "ready",
            json.dumps({"source_sha256": "0" * 64}), "test"))
    with pytest.raises(ValueError, match="inspection|[Ii]nspection|hash"):
        registry.resolve("fixture", 1)


def test_out_of_sqlite_range_version_is_actionable(tmp_path):
    registry = AssetRegistry(tmp_path / "library")
    with pytest.raises(ValueError, match="version"):
        registry.get("fixture", 2 ** 63)
