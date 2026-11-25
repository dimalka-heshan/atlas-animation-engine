import io
import json
import struct

import pytest

from engine.assets.acquisition import _encode_glb, download
from engine.assets.glb import inspect_glb
from engine.assets.providers import PolyHaven


def test_polyhaven_variant_resolver_prefers_best_affordable_available_size():
    item = {"url": "https://dl.polyhaven.org/example.gltf", "size": 20, "md5": "0" * 32}
    files = {"gltf": {"1k": {"gltf": item | {"include": {"model.bin": item}}},
                      "4k": {"gltf": item | {"include": {"model.bin": item | {"size": 80}}}}}}
    variants = PolyHaven.variants(files, "environment")
    assert [(v["resolution"], v["bytes"]) for v in variants] == [("1k", 40), ("4k", 100)]
    assert PolyHaven.pick_variant(variants, 100, 2048) == "1k"
    assert PolyHaven.pick_variant(variants, 100, 4096) == "4k"
    with pytest.raises(ValueError, match="budget"):
        PolyHaven.pick_variant(variants, 10, 4096)


def test_temporary_download_url_never_enters_metadata_and_cache_can_reuse_it(tmp_path):
    url = "https://files.example.invalid/archive.zip?signature=private"
    permanent = "https://example.invalid/models/one"
    received = []

    class Response(io.BytesIO):
        headers = {"Content-Length": "4"}

    def opener(source):
        received.append(source)
        return Response(b"data")

    options = {"cache_key": "model-one-at-revision-a", "recorded_url": permanent,
               "validate_url": lambda supplied: None, "open_url": opener}
    blob, report = download(url, tmp_path, 100, expected_size=4, **options)
    second, reused = download(url.replace("private", "next"), tmp_path, 100, expected_size=4, **options)
    assert blob == second and reused["cache_hit"]
    assert received == [url] and report["url"] == permanent
    assert "signature" not in next((tmp_path / "downloads").iterdir()).read_text()


def test_optical_pbr_values_are_allowed_only_in_the_explicit_profile(tmp_path):
    source = tmp_path / "pine.glb"
    extensions = {"KHR_materials_ior": {"ior": 1.45},
                  "KHR_materials_specular": {"specularColorFactor": [.05, .05, .05]}}
    document = {"asset": {"version": "2.0"}, "extensionsUsed": list(extensions),
                "materials": [{"extensions": extensions}]}
    source.write_bytes(_encode_glb(document, b""))
    with pytest.raises(ValueError, match="extensions"):
        inspect_glb(source)
    assert inspect_glb(source, "pbr")["profile"] == "pbr"
    extensions["KHR_materials_specular"]["specularTexture"] = {"index": 0}
    source.write_bytes(_encode_glb(document, b""))
    with pytest.raises(ValueError, match="specular"):
        inspect_glb(source, "pbr")


def test_derivation_selects_a_unique_root_mesh_and_removes_display_offset(tmp_path):
    from engine.assets.acquisition import isolate_root_mesh

    source = tmp_path / "modules.glb"
    source.write_bytes(_encode_glb({"asset": {"version": "2.0"}, "scene": 0,
        "scenes": [{"nodes": [0, 1]}], "nodes": [{"mesh": 0, "name": "Wall"},
            {"mesh": 1, "name": "Gate", "translation": [15, 0, 10]}],
        "meshes": [{"name": "Wall mesh", "primitives": []}, {"name": "Gate mesh", "primitives": []}]}, b""))
    isolated = isolate_root_mesh(source, "Gate")
    size = struct.unpack_from("<I", isolated, 12)[0]
    payload = json.loads(isolated[20:20+size])
    assert payload["scenes"][0]["nodes"] == [0]
    assert payload["nodes"] == [{"mesh": 0, "name": "Gate"}]
    assert [mesh["name"] for mesh in payload["meshes"]] == ["Gate mesh"]
    with pytest.raises(ValueError, match="unique root mesh"):
        isolate_root_mesh(source, "Absent")


def test_total_cache_budget_rejects_new_content_without_leaving_a_partial_blob(tmp_path, monkeypatch):
    from engine.assets import acquisition

    monkeypatch.setenv("ATLAS_ASSET_CACHE_MIB", "1")
    blobs = tmp_path / "blobs"
    blobs.mkdir()
    (blobs / ("0" * 64)).write_bytes(b"0" * (acquisition.MIB - 2))

    class Response(io.BytesIO):
        headers = {"Content-Length": "4"}

    monkeypatch.setattr(acquisition, "request", lambda source: Response(b"data"))
    with pytest.raises(ValueError, match="total cache budget"):
        download("https://dl.polyhaven.org/example", tmp_path, 64, expected_size=4)
    assert [p.name for p in blobs.iterdir()] == ["0" * 64]
