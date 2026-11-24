import io
import hashlib
import stat
import zipfile

import pytest

from engine.assets.acquisition import download, pack_gltf, unpack_models


def test_archive_rejects_traversal_even_outside_model_selection():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('pack/model.gltf', '{}')
        z.writestr('pack/../bad.exe', 'bad')
    with zipfile.ZipFile(archive) as z, pytest.raises(ValueError, match='path'):
        unpack_models(z)


def test_missing_gltf_dependency_is_rejected():
    payload = b'{"asset":{"version":"2.0"},"buffers":[{"uri":"missing.bin","byteLength":4}]}'
    with pytest.raises(ValueError, match='dependency'):
        pack_gltf(payload, lambda name: None)


@pytest.mark.parametrize('uri', ['https://example.com/a.bin','../secret.bin','a%2fb.bin','C:/file.bin'])
def test_gltf_dependency_must_be_a_same_folder_name(uri):
    import json
    payload = json.dumps({'asset':{'version':'2.0'}, 'buffers':[{'uri':uri,'byteLength':4}]}).encode()
    with pytest.raises(ValueError, match='dependency'):
        pack_gltf(payload, lambda name: b'0000')


def test_archive_rejects_symlink_and_executable():
    for filename, mode in [("body.gltf", stat.S_IFLNK), ("body.exe", stat.S_IFREG)]:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            item = zipfile.ZipInfo(filename)
            item.create_system = 3
            item.external_attr = (mode | 0o644) << 16
            z.writestr(item, "payload")
        with zipfile.ZipFile(archive) as z, pytest.raises(ValueError, match="linked|executable"):
            unpack_models(z)


def test_download_checks_hash_budget_and_reuses_verified_bytes(tmp_path, monkeypatch):
    import engine.assets.acquisition as acquisition
    class Response(io.BytesIO):
        headers = {"Content-Length": "8"}
    calls = []
    def request(url):
        calls.append(url)
        return Response(b"official")
    monkeypatch.setattr(acquisition, "request", request)
    url = "https://dl.polyhaven.org/file/test.hdr"
    path, first = download(url, tmp_path, 16, expected_size=8,
                           expected_md5=hashlib.md5(b"official", usedforsecurity=False).hexdigest())
    assert first["sha256"] == hashlib.sha256(b"official").hexdigest()
    assert download(url, tmp_path, 16)[1]["cache_hit"]
    assert len(calls) == 1
    path.write_bytes(b"tampered")
    assert not download(url, tmp_path, 16)[1]["cache_hit"]
    assert path.read_bytes() == b"official"
    with pytest.raises(ValueError, match="budget"):
        download(url, tmp_path, 7, expected_size=8)


def test_offline_catalog_seeded_filter_and_page(tmp_path):
    from engine.assets.providers import search_catalog, synchronize
    assert search_catalog(tmp_path / "empty") == []
    synchronize("kaykit", tmp_path)
    rows = search_catalog(tmp_path, "medieval", category="environment", seed=10)
    assert len(rows) == 10
    assert search_catalog(tmp_path, "medieval", category="environment", seed=10, limit=3, offset=2) == rows[2:5]
    assert search_catalog(tmp_path, "medieval", style="photorealistic") == []
    assert {row["id"] for row in search_catalog(tmp_path, category="character")} == {"kaykit-knight", "kaykit-mage"}


def test_environment_media_can_resolve_prior_fingerprint(tmp_path):
    from engine.assets.environment_media import media_fingerprint, resolve_media
    from engine.core.models import Project
    from engine.storage.jobs import atomic_json
    ident = "polyhaven-one"
    data = b"fixture HDR bytes"
    digest = hashlib.sha256(data).hexdigest()
    (tmp_path / "blobs").mkdir()
    (tmp_path / "blobs" / digest).write_bytes(data)
    record = {"catalog": {"provider": "polyhaven", "id": ident, "license_id": "CC0-1.0", "category": "hdri"},
              "license_text": "Fixture license", "files": [{"channel": "hdri", "sha256": digest, "bytes": len(data)}]}
    fingerprint = media_fingerprint(record)
    atomic_json(tmp_path / "media-versions" / ident / f"{fingerprint}.json", record)
    atomic_json(tmp_path / "acquired" / f"{ident}.json", {"latest": "different media"})
    scene = {"environment": {"hdri": {"id": ident, "fingerprint": fingerprint}}}
    project = Project.model_validate({"id": "old-media", "schema_version": "1.3", "scene": scene})
    assert resolve_media(project, tmp_path) == [record]
    (tmp_path / "blobs" / digest).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="changed"):
        resolve_media(project, tmp_path)
