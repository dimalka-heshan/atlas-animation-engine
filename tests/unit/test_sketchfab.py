from contextlib import closing
import io
from http.client import HTTPConnection
import json
import socket
from threading import Thread
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from zipfile import ZipFile

import pytest

from engine.assets import sketchfab as sf


UID = "0" * 32
BY_UID = "322a749bcfa841b29dff1e8a1bb74b0b"
BY_URL = "https://creativecommons.org/licenses/by/4.0/"
SIGNED = f"https://sketchfab-prod-media.s3.amazonaws.com/archives/{UID}/gltf/model.zip?Signature=secret"


class Response(io.BytesIO):
    def __init__(self, value):
        super().__init__(value)
        self.headers = {"Content-Length": str(len(value))}


def model(**updates):
    return {"uid": UID, "isDownloadable": True, "isAgeRestricted": False, "name": "Test castle",
            "user": {"username": "artist", "displayName": "Test Artist"},
            "viewerUrl": f"https://sketchfab.com/3d-models/test-castle-{UID}",
            "publishedAt": "2023-01-01T00:00:00", "updatedAt": "2024-01-01T00:00:00",
            "license": {"uid": BY_UID, "label": "CC Attribution"},
            "categories": [{"name": "architecture"}], "tags": [{"slug": "photogrammetry"}],
            "thumbnails": {"images": [{"url": f"https://media.sketchfab.com/models/{UID}/thumbnails/a/b.jpeg",
                                       "width": 256}]}, "archives": {"gltf": {"size": 1000}}} | updates


def test_public_discovery_paginates_and_filters_without_following_supplied_url(tmp_path, monkeypatch):
    from engine.assets.providers import search_catalog, store_catalog

    calls = []

    def api(url, **kwargs):
        assert not kwargs
        parts = urlsplit(url)
        assert parts.netloc == "api.sketchfab.com" and parts.path == "/v3/search"
        params = parse_qs(parts.query)
        assert params["downloadable"] == ["true"]
        assert params["q"] == ["castle"]
        assert params["categories"] == ["architecture"]
        assert params["tags"] == ["photogrammetry"]
        calls.append((params["license"][0], params.get("cursor")))
        if params["license"] == ["cc0"]:
            return {"results": [model()], "cursors": {"next": None}}
        if "cursor" in params:
            return {"results": [model(), model(isDownloadable=False)], "cursors": {"next": None}}
        return {"results": [model(), model(license={"uid": "bad", "label": "CC Attribution"}),
                            model(uid="a" * 32, categories=[{"name": "mismatched"}])],
                "next": "https://untrusted.example/collect", "cursors": {"next": "24"}}

    monkeypatch.setattr(sf, "_json_request", api)
    result = sf.Sketchfab().discover(query="castle", categories=("architecture",), tags=("photogrammetry",), pages=2)
    assert len(calls) == 3 and ("by", ["24"]) in calls
    assert [item["id"] for item in result] == [f"sketchfab-{UID}"]
    assert result[0]["source_url"].endswith(UID)
    assert result[0]["thumbnail_url"].startswith("https://media.sketchfab.com/")
    assert "artist" in result[0]["attribution"]
    store_catalog("sketchfab", tmp_path, result, sf.Sketchfab().label, replace=True)
    stored = search_catalog(tmp_path, "photogrammetry castle", provider="sketchfab")
    assert len(stored) == 1 and stored[0]["attribution"] == result[0]["attribution"]


@pytest.mark.parametrize("status, message", [(302, "redirect"), (429, "rate limit"), (503, "503")])
def test_api_errors_are_actionable_and_do_not_expose_remote_content(monkeypatch, status, message):
    class Opener:
        def open(self, request, timeout):
            assert timeout == 25
            raise HTTPError(request.full_url + "?secret", status, "secret", {}, None)

    monkeypatch.setattr(sf, "build_opener", lambda handler: Opener())
    with pytest.raises(ValueError, match=message) as exc:
        sf._json_request(f"https://api.sketchfab.com/v3/models/{UID}/download", bearer="test-secret")
    assert "secret" not in str(exc.value)
    assert exc.value.__suppress_context__


def test_oauth_refresh_uses_post_body_and_retries_a_401_once(monkeypatch):
    calls = []

    def api(url, *, bearer=None, form=None):
        calls.append((url, bearer, form))
        if form:
            return {"access_token": "refreshed", "refresh_token": "rotated", "expires_in": 600,
                    "token_type": "Bearer"}
        if bearer == "stale":
            raise sf.SketchfabAPIError(401)
        return {"gltf": {"url": SIGNED, "size": 1000, "expires": 300}}

    monkeypatch.setattr(sf, "_json_request", api)
    oauth = sf.SketchfabOAuth("stale", "first-refresh", "registered-app", "registered-secret")
    assert oauth.download_ticket(UID)["gltf"]["url"] == SIGNED
    assert len(calls) == 3
    assert calls[1] == (sf.TOKEN_URL, None, {"grant_type": "refresh_token", "client_id": "registered-app",
                                            "client_secret": "registered-secret", "refresh_token": "first-refresh"})
    assert [call[1] for call in calls] == ["stale", None, "refreshed"]
    assert oauth.refresh_token == "rotated"
    assert "refreshed" not in repr(oauth) and "registered-secret" not in repr(oauth)


def test_oauth_refreshes_known_expiry_before_api_and_reports_missing_credentials(monkeypatch):
    for name in ("ACCESS_TOKEN", "REFRESH_TOKEN", "TOKEN_EXPIRES_AT", "CLIENT_ID", "CLIENT_SECRET"):
        monkeypatch.delenv(f"ATLAS_SKETCHFAB_{name}", raising=False)
    with pytest.raises(ValueError, match="OAuth"):
        sf.SketchfabOAuth.from_environment().download_ticket(UID)
    oauth = sf.SketchfabOAuth("stale", "refresh", "client", "secret", expires_at=1)
    calls = []

    def api(url, *, bearer=None, form=None):
        calls.append((url, bearer))
        return {"access_token": "new", "expires_in": 90} if form else {}

    monkeypatch.setattr(sf, "_json_request", api)
    oauth.download_ticket(UID)
    assert calls == [(sf.TOKEN_URL, None), (f"{sf.API}/models/{UID}/download", "new")]


@pytest.mark.parametrize("url", ["http://sketchfab-prod-media.s3.amazonaws.com/archives/x/gltf/x.zip",
    "https://sketchfab-prod-media.s3.amazonaws.com.evil.example/archives/x/gltf/x.zip",
    f"https://user@sketchfab-prod-media.s3.amazonaws.com/archives/{UID}/gltf/x.zip",
    f"https://sketchfab-prod-media.s3.amazonaws.com/archives/{UID}/gltf/../secret.zip",
    f"https://sketchfab-prod-media.s3.amazonaws.com/archives/{UID}/gltf/%2e%2e.zip",
    f"https://sketchfab-prod-media.s3.amazonaws.com/archives/{UID}/usdz/a.zip",
    f"https://api.sketchfab.com/archives/{UID}/gltf/a.zip"])
def test_signed_archive_requires_the_documented_host_and_layout(url):
    with pytest.raises(ValueError, match="archive"):
        sf._check_archive_url(url)


def test_download_registers_textured_glb_and_reuses_cache_without_signed_urls(tmp_path, monkeypatch):
    document = {"asset": {"version": "2.0"}, "buffers": [{"uri": "scene.bin", "byteLength": 4}],
                "images": [{"uri": "textures/base.png"}]}
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("scene.gltf", json.dumps(document))
        archive.writestr("scene.bin", b"0000")
        archive.writestr("textures/base.png", b"\x89PNG\r\n\x1a\n")
    body = stream.getvalue()
    opened = []

    def opener(request):
        opened.append(request.full_url)
        assert not request.has_header("Authorization")
        return Response(body)

    def api(url, *, bearer=None):
        if url.endswith("/download"):
            assert bearer == "access-secret"
            signature = "secret-two" if opened else "secret-one"
            return {"gltf": {"url": SIGNED.replace("secret", signature), "size": len(body), "expires": 300}}
        assert bearer is None
        return model(license={"uri": f"{sf.API}/licenses/{BY_UID}", "slug": "by", "url": BY_URL})

    monkeypatch.setattr(sf, "_open", opener)
    monkeypatch.setattr(sf, "_json_request", api)
    monkeypatch.setattr(sf, "fetch_bytes", lambda url, limit: b"Creative Commons legal code")
    monkeypatch.setenv("ATLAS_SKETCHFAB_ACCESS_TOKEN", "access-secret")
    monkeypatch.delenv("ATLAS_SKETCHFAB_TOKEN_EXPIRES_AT", raising=False)
    adapter = sf.Sketchfab()
    entry = {"id": f"sketchfab-{UID}", "uid": UID, "license_id": "CC-BY-4.0"}
    first = adapter.acquire(entry, tmp_path / "cache", tmp_path / "library", 1024 * 1024)
    second = adapter.acquire(entry, tmp_path / "cache", tmp_path / "library", 1024 * 1024)
    rights = first["asset"]["provenance"]
    assert rights["creator"] == "Test Artist (@artist)" and rights["license_id"] == "CC-BY-4.0"
    assert rights["approval"] == "approved" and "Sketchfab" in rights["attribution"]
    assert first["asset"]["version"] == second["asset"]["version"] == 1
    assert second["download"]["cache_hit"] and len(opened) == 1
    blob = tmp_path / "cache" / "blobs" / first["download"]["sha256"]
    blob.write_bytes(b"0" * len(body))
    repaired = adapter.acquire(entry, tmp_path / "cache", tmp_path / "library", 1024 * 1024)
    assert not repaired["download"]["cache_hit"] and len(opened) == 2
    assert repaired["asset"]["version"] == 1 and blob.read_bytes() == body
    assert "secret" not in json.dumps(first)
    assert all("secret" not in file.read_text() for file in (tmp_path / "cache").rglob("*.json"))


def test_acquisition_rechecks_current_license_before_using_oauth(tmp_path, monkeypatch):
    def api(url, **kwargs):
        assert url == f"{sf.API}/models/{UID}" and not kwargs
        return model(license={"uri": f"{sf.API}/licenses/{BY_UID}", "slug": "by", "url": BY_URL + "changed"})

    monkeypatch.setattr(sf, "_json_request", api)
    with pytest.raises(ValueError, match="license"):
        sf.Sketchfab().acquire({"id": f"sketchfab-{UID}", "uid": UID, "license_id": "CC-BY-4.0"},
                              tmp_path / "cache", tmp_path / "library", 1024)


def test_network_error_is_redacted(monkeypatch):
    def fail(_request):
        raise URLError("sensitive URL or credentials")

    monkeypatch.setattr(sf, "_open", fail)
    with pytest.raises(ValueError, match="network request failed") as exc:
        sf._json_request(f"{sf.API}/models/{UID}/download", bearer="test-secret")
    assert "sensitive" not in str(exc.value)


@pytest.mark.parametrize("url", ["https://localhost:8412/callback", "http://0.0.0.0:8412/callback",
    "http://127.0.0.1/callback", "http://127.0.0.1:8412/callback?x=1"])
def test_oauth_loopback_rejects_unregistered_uri_shapes(url):
    with pytest.raises(ValueError, match="loopback"):
        sf._check_callback_uri(url)


def test_browser_flow_checks_state_and_exchanges_code_without_logging(monkeypatch, capsys):
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    redirect = f"http://127.0.0.1:{port}/callback"
    oauth = sf.SketchfabOAuth(client_id="registered-client", client_secret="private-client-secret")
    statuses, exchanges, threads = [], [], []

    def open_browser(url):
        endpoint, _, query = url.partition("?")
        params = parse_qs(query)
        assert endpoint == sf.AUTHORIZE_URL and params["response_type"] == ["code"]
        assert params["redirect_uri"] == [redirect] and "private-client-secret" not in url

        def call_back():
            for state in ("forged", params["state"][0]):
                with closing(HTTPConnection("127.0.0.1", port, timeout=5)) as connection:
                    connection.request("GET", "/callback?" + urlencode({"state": state, "code": "private-code"}))
                    response = connection.getresponse()
                    statuses.append((response.status, response.read()))

        thread = Thread(target=call_back, daemon=True)
        threads.append(thread)
        thread.start()
        return True

    def exchange(url, *, form):
        exchanges.append((url, form))
        return {"access_token": "private-access", "refresh_token": "private-refresh", "expires_in": 600}

    monkeypatch.setattr(sf.webbrowser, "open", open_browser)
    monkeypatch.setattr(sf, "_json_request", exchange)
    sf._authorize(oauth, redirect)
    threads[0].join(timeout=5)
    assert [status for status, _ in statuses] == [400, 200]
    assert all(b"private" not in response for _, response in statuses)
    assert exchanges == [(sf.TOKEN_URL, {"grant_type": "authorization_code", "code": "private-code",
                                        "client_id": "registered-client", "client_secret": "private-client-secret",
                                        "redirect_uri": redirect})]
    assert oauth.access_token == "private-access" and oauth.refresh_token == "private-refresh"
    output = capsys.readouterr()
    assert not output.err and not output.out


def test_bearer_cannot_be_attached_to_public_or_foreign_endpoints(monkeypatch):
    monkeypatch.setattr(sf, "_open", lambda request: pytest.fail("Credentialed request escaped validation"))
    for url in (f"{sf.API}/search", f"{sf.API}/models/{UID}/download?inject=true", SIGNED, sf.TOKEN_URL):
        with pytest.raises(ValueError):
            sf._json_request(url, bearer="protected")
    with pytest.raises(ValueError, match="fixed Sketchfab token endpoint"):
        sf._json_request(SIGNED, form={"client_secret": "protected"})


def test_auth_check_uses_me_endpoint_and_keeps_profile_private(monkeypatch):
    def api(url, *, bearer):
        assert url == f"{sf.API}/me" and bearer == "access-secret"
        return {"uid": UID, "email": "private-email@example.com"}

    monkeypatch.setenv("ATLAS_SKETCHFAB_ACCESS_TOKEN", "access-secret")
    monkeypatch.delenv("ATLAS_SKETCHFAB_TOKEN_EXPIRES_AT", raising=False)
    monkeypatch.setattr(sf, "_json_request", api)
    assert sf.sketchfab_auth_status() == {"provider": "sketchfab", "authenticated": True}
