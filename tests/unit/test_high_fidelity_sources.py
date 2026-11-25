import hashlib
import io
import json
import struct
from zipfile import ZipFile

import pytest

from engine.assets import acquisition
from engine.assets.environment_media import resolve_media, snapshot_media
from engine.assets.providers import acquire, synchronize
from engine.core.models import Project


API = "https://api.polyhaven.com"
CDN = "https://dl.polyhaven.org/test"
AMBIENT = "https://ambientcg.com/api/v3/assets"
LICENSE = "https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt"


def route_provider_requests(monkeypatch, routes):
    class Response(io.BytesIO):
        def __init__(self, data):
            super().__init__(data)
            self.headers = {"Content-Length": str(len(data))}

    def request(url):
        acquisition.check_url(url)
        data = routes[url]
        return Response(data if isinstance(data, bytes) else json.dumps(data).encode())

    monkeypatch.setattr(acquisition, "request", request)


def provider_file(url, data):
    return {"url": url, "size": len(data), "md5": hashlib.md5(data, usedforsecurity=False).hexdigest()}


def test_polyhaven_model_packages_are_embedded_and_budgeted(tmp_path, monkeypatch):
    model = json.dumps({
        "asset": {"version": "2.0"}, "buffers": [{"uri": "rock.bin", "byteLength": 4}],
        "images": [{"uri": "textures/rock.jpg"}],
    }).encode()
    binary = b"abcd"
    texture = b"\xff\xd8\xfffixture"
    model_url = f"{CDN}/rock.gltf"
    deps = {"rock.bin": provider_file(f"{CDN}/rock.bin", binary),
            "textures/rock.jpg": provider_file(f"{CDN}/rock.jpg", texture)}
    route_provider_requests(monkeypatch, {
        f"{API}/assets?t=hdris": {}, f"{API}/assets?t=textures": {},
        f"{API}/assets?t=models": {"Rock_01": {"name": "Rock", "tags": ["stone"]}},
        f"{API}/files/Rock_01": {"gltf": {"2k": {"gltf": provider_file(model_url, model) | {"include": deps}}}},
        model_url: model, f"{CDN}/rock.bin": binary, f"{CDN}/rock.jpg": texture, LICENSE: b"CC0 1.0 Universal",
    })
    cache, library = tmp_path / "cache", tmp_path / "library"
    entries = synchronize("polyhaven", cache)["entries"]
    assert [(e["id"], e["category"]) for e in entries] == [("polyhaven-rock_01", "environment")]
    total = len(model) + len(binary) + len(texture)
    with pytest.raises(ValueError, match="budget"):
        acquire("polyhaven-rock_01", cache, library, total - 1, resolution="2k")
    result = acquire("polyhaven-rock_01", cache, library, total, resolution="2k", source_format="gltf")
    assert result["asset"]["container"]["texture_count"] == 1
    assert result["asset"]["container"]["external_dependencies"] == []
    assert result["asset"]["provenance"]["license_id"] == "CC0-1.0"
    assert {file["member"] for file in result["files"]} == {"rock.gltf", "rock.bin", "textures/rock.jpg"}
    again = acquire("polyhaven-rock_01", cache, library, total, resolution="2k")
    assert again["asset"]["version"] == result["asset"]["version"] == 1
    assert all(file["cache_hit"] for file in again["files"])


@pytest.mark.parametrize("uri", ["../rock.jpg", "textures/../rock.jpg", "textures%2frock.jpg",
                                "https://dl.polyhaven.org/rock.jpg", "textures/channels/rock.jpg"])
def test_polyhaven_texture_subfolder_still_rejects_other_paths(uri):
    model = json.dumps({"asset": {"version": "2.0"}, "buffers": [{"uri": "rock.bin", "byteLength": 4}],
                        "images": [{"uri": uri}]}).encode()
    visited = []

    def read(name):
        visited.append(name)
        return b"abcd"

    with pytest.raises(ValueError, match="Unsafe glTF dependency"):
        acquisition.pack_gltf(model, read, texture_subdirectory=True)
    assert visited == ["rock.bin"]


def test_ambientcg_material_snapshots_pbr_channels(tmp_path, monkeypatch):
    archive = io.BytesIO()
    with ZipFile(archive, "w") as output:
        for channel in ("Color", "Roughness", "NormalGL", "NormalDX", "Metalness", "Displacement"):
            pixels = "same-gray" if channel in {"Color", "Roughness"} else channel
            output.writestr(f"Wood001_2K-PNG_{channel}.png", b"\x89PNG\r\n\x1a\n" + pixels.encode())
    body = archive.getvalue()
    name = "Wood001_2K-PNG.zip"
    url = f"https://ambientcg.com/get?file={name}"
    metadata = {"id": "Wood001", "tags": ["wood"], "releaseDate": "2025-01-29"}
    route_provider_requests(monkeypatch, {
        f"{AMBIENT}?type=material&sort=alphabet&limit=250&offset=0&include=tags,releaseDate":
            {"totalResults": 1, "assets": [metadata]},
        f"{AMBIENT}?type=material&id=Wood001&include=downloads": {"assets": [metadata | {
            "downloads": [{"attributes": "2K-PNG", "extension": "zip", "url": url, "size": len(body)}]}]},
        url: body, LICENSE: b"CC0 1.0 Universal",
    })
    cache = tmp_path / "cache"
    synchronize("ambientcg", cache)
    result = acquire("ambientcg-wood001", cache, tmp_path / "library", len(body), resolution="2k", source_format="png")
    assert {item["channel"] for item in result["files"]} == {"Diffuse", "Rough", "nor_gl", "Metal", "Displacement"}
    assert result["catalog"]["source_url"] == "https://ambientcg.com/a/Wood001"
    assert result["download"]["sha256"] == hashlib.sha256(body).hexdigest()
    project = Project.model_validate({"id": "wood-court", "schema_version": "1.3", "scene": {"environment": {
        "ground_texture": {"id": "ambientcg-wood001", "fingerprint": result["fingerprint"]}}}})
    directory = tmp_path / "job"
    directory.mkdir()
    snapshots = snapshot_media(resolve_media(project, cache), cache, directory)
    channels = {item["channel"]: item for item in snapshots[0]["files"]}
    assert channels["Diffuse"]["sha256"] == channels["Rough"]["sha256"]
    assert channels["Diffuse"]["source_file"] != channels["Rough"]["source_file"]
    for item in snapshots[0]["files"]:
        assert item["source_file"].endswith(".png")
        assert (directory / item["source_file"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_smithsonian_reframes_the_reviewed_chair_in_meters(tmp_path, monkeypatch):
    package = "ff607e3c-3d88-4422-a246-3976aa4839dc"
    filename = "chair-(england)-1750-60-150k-4096.glb"
    api = f"https://3d-api.si.edu/api/v1.0/content/file/search?model_url={package}&file_type=glb"
    source = f"https://3d-api.si.edu/content/document/3d_package:{package}/resources/{filename}"
    document = json.dumps({"asset": {"version": "2.0"}, "nodes": [{}], "scenes": [{"nodes": [0]}]}).encode()
    document += b" " * (-len(document) % 4)
    glb = struct.pack("<4sIIII", b"glTF", 2, 20 + len(document), len(document), 0x4E4F534A) + document
    row = {"uri": source, "usage": "Download3D", "file_type": "glb", "model_url": f"3d_package:{package}",
           "file_size": len(glb), "gltf_orientation_compliant": True}
    route_provider_requests(monkeypatch, {
        api: {"rows": [{"title": "Side Chair", "content": row}]}, source: glb, LICENSE: b"CC0 1.0 Universal",
    })
    cache, library = tmp_path / "cache", tmp_path / "library"
    entries = synchronize("smithsonian", cache)["entries"]
    assert [(entry["id"], entry["license_id"], entry["accession"]) for entry in entries] == [
        ("smithsonian-rococo-side-chair", "CC0-1.0", "2006-5-1")]
    result = acquire(entries[0]["id"], cache, library, source_format="glb")
    asset = result["asset"]
    blob = (library / "blobs" / f"{asset['sha256']}.glb").read_bytes()
    chunk_size = struct.unpack_from("<I", blob, 12)[0]
    converted = json.loads(blob[20:20 + chunk_size])
    root = converted["nodes"][converted["scenes"][0]["nodes"][0]]
    assert root == {"scale": [0.001, 0.001, 0.001], "children": [0]}
    assert result["download"]["sha256"] == hashlib.sha256(glb).hexdigest()
    assert asset["provenance"]["render_allowed"] is True
    assert asset["provenance"]["source_url"].endswith(f"side-chair%3A{package}")
