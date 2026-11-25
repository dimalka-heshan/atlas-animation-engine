import io

import pytest

from engine.assets.acquisition import download
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
