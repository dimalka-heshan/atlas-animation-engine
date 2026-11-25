"""Public Sketchfab discovery and user-authorized glTF archive acquisition."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from hmac import compare_digest
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import webbrowser
from zipfile import BadZipFile, ZipFile

from engine.assets.acquisition import MIB, archive_model, download, fetch_bytes, unpack_models
from engine.assets.models import Provenance
from engine.assets.registry import AssetRegistry

API = "https://api.sketchfab.com/v3"
AUTHORIZE_URL = "https://sketchfab.com/oauth2/authorize/"
TOKEN_URL = "https://sketchfab.com/oauth2/token/"
ARCHIVE_HOST = "sketchfab-prod-media.s3.amazonaws.com"
DEFAULT_QUERIES = ("medieval house", "ancient ruins", "castle", "historical furniture",
                   "historical artifacts", "photogrammetry landscape")
# The official /v3/licenses endpoint supplies these versioned license identities.
LICENSES = {
    "7c23a1ba438d4306920229c12afcb5f9": ("cc0", "CC0-1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
    "322a749bcfa841b29dff1e8a1bb74b0b": ("by", "CC-BY-4.0", "https://creativecommons.org/licenses/by/4.0/"),
}
UID = re.compile(r"[a-f0-9]{32}")
SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,99}")


class SketchfabAPIError(ValueError):
    def __init__(self, status: int):
        self.status = status
        messages = {401: "Sketchfab rejected the OAuth access token",
                    403: "Sketchfab denied access to the requested resource",
                    404: "Sketchfab could not find the requested resource",
                    429: "Sketchfab rate limit reached. Wait before retrying."}
        message = ("Sketchfab rejected an unexpected endpoint redirect" if 300 <= status < 400
                   else messages.get(status, f"Sketchfab request failed (HTTP {status})"))
        super().__init__(message)


def _parts(url):
    if not isinstance(url, str) or len(url) > 8192 or re.search(r"[\x00-\x20\x7f\\]", url):
        raise ValueError("Invalid URL")
    return urlsplit(url)


def _https(url, host):
    parts = _parts(url)
    if parts.scheme != "https" or parts.netloc != host or parts.fragment:
        raise ValueError("Unexpected Sketchfab HTTPS endpoint")
    return parts


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(request):
    return build_opener(_RejectRedirect()).open(request, timeout=25)


def _secret(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[\x21-\x7e]{1,4096}", value))


def _json_request(url, *, bearer=None, form=None):
    headers = {"User-Agent": "ATLAS-Animation/0.5.2", "Accept": "application/json", "Accept-Encoding": "identity"}
    data = None
    if form is not None:
        if url != TOKEN_URL or bearer is not None:
            raise ValueError("OAuth exchange requires the fixed Sketchfab token endpoint")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urlencode(form).encode("ascii")
    else:
        parts = _https(url, "api.sketchfab.com")
        if bearer is not None:
            supported = parts.path == "/v3/me" or re.fullmatch(r"/v3/models/[a-f0-9]{32}/download", parts.path)
            if not supported or parts.query or not _secret(bearer):
                raise ValueError("Sketchfab bearer credentials require an approved authenticated API endpoint")
            headers["Authorization"] = f"Bearer {bearer}"
        elif parts.path != "/v3/search" and not (re.fullmatch(r"/v3/models/[a-f0-9]{32}", parts.path) and not parts.query):
            raise ValueError("Unexpected Sketchfab public API endpoint")
    limit = MIB if form is not None else 4 * MIB
    try:
        with _open(Request(url, data=data, headers=headers)) as response:
            if response.headers.get("Content-Encoding", "identity") != "identity":
                raise ValueError("Unexpected compressed Sketchfab API response")
            body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError("Sketchfab API response exceeds its byte limit")
        result = json.loads(body)
    except HTTPError as exc:
        exc.close()
        raise SketchfabAPIError(exc.code) from None
    except (OSError, HTTPException, UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("Sketchfab network request failed or returned invalid JSON") from None
    if not isinstance(result, dict):
        raise ValueError("Sketchfab returned an invalid API response")
    return result


@dataclass
class SketchfabOAuth:
    access_token: str = field(default="", repr=False)
    refresh_token: str = field(default="", repr=False)
    client_id: str = field(default="", repr=False)
    client_secret: str = field(default="", repr=False)
    expires_at: float | None = None

    @classmethod
    def from_environment(cls):
        expires = os.environ.get("ATLAS_SKETCHFAB_TOKEN_EXPIRES_AT", "")
        if expires and not re.fullmatch(r"[0-9]{1,12}", expires):
            raise ValueError("ATLAS_SKETCHFAB_TOKEN_EXPIRES_AT must be UTC Unix seconds")
        return cls(*(os.environ.get("ATLAS_SKETCHFAB_" + name, "") for name in
                     ("ACCESS_TOKEN", "REFRESH_TOKEN", "CLIENT_ID", "CLIENT_SECRET")),
                   expires_at=int(expires) if expires else None)

    def _exchange(self, form):
        if not _secret(self.client_id) or not _secret(self.client_secret):
            raise ValueError("Sketchfab OAuth requires the registered client ID and secret")
        response = _json_request(TOKEN_URL, form=form | {"client_id": self.client_id, "client_secret": self.client_secret})
        access, refresh, expires = (response.get(k) for k in ("access_token", "refresh_token", "expires_in"))
        token_type = response.get("token_type", "Bearer")
        if (not _secret(access) or (refresh is not None and not _secret(refresh))
                or token_type not in ("Bearer", "bearer") or type(expires) is not int or not 0 < expires <= 365 * 86400):
            raise ValueError("Sketchfab returned an invalid OAuth token response")
        self.access_token = access
        self.refresh_token = refresh or self.refresh_token
        self.expires_at = time.time() + expires

    def _refresh(self):
        if not _secret(self.refresh_token):
            raise ValueError("Sketchfab OAuth requires a fresh access token or browser login")
        self._exchange({"grant_type": "refresh_token", "refresh_token": self.refresh_token})

    def download_ticket(self, uid):
        if not isinstance(uid, str) or not UID.fullmatch(uid):
            raise ValueError("Invalid Sketchfab model UID")
        return self._authorized_request(f"{API}/models/{uid}/download")

    def _authorized_request(self, url):
        if not _secret(self.access_token) or (self.expires_at is not None and self.expires_at <= time.time() + 30):
            self._refresh()
        try:
            return _json_request(url, bearer=self.access_token)
        except SketchfabAPIError as exc:
            if exc.status != 401 or not self.refresh_token:
                raise
        self._refresh()
        return _json_request(url, bearer=self.access_token)


def _check_callback_uri(url):
    if not isinstance(url, str) or not re.fullmatch(r"http://(?:127\.0\.0\.1|localhost):[0-9]{1,5}/[A-Za-z0-9_-]{1,80}", url):
        raise ValueError("Set ATLAS_SKETCHFAB_REDIRECT_URI to the registered HTTP loopback address, port and path")
    parts = urlsplit(url)
    if not 1024 <= int(parts.netloc.rpartition(":")[2]) <= 65535:
        raise ValueError("Sketchfab OAuth loopback port must be between 1024 and 65535")
    return parts


def _callback_code(query, state):
    try:
        params = parse_qs(query, strict_parsing=True, max_num_fields=8)
    except ValueError:
        return None
    received = params.get("state", [])
    if len(received) != 1 or not received[0].isascii() or not compare_digest(received[0], state):
        return None
    if "error" in params:
        return ""
    code = params.get("code", [])
    return code[0] if len(code) == 1 and _secret(code[0]) else None


class _LoopbackServer(HTTPServer):
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(3)
        return connection, address


def _authorize(oauth, redirect_uri):
    parts = _check_callback_uri(redirect_uri)
    state = secrets.token_urlsafe(32)
    callbacks = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            path, _, query = self.path.partition("?")
            code = (_callback_code(query, state) if path == parts.path and self.headers.get("Host") == parts.netloc
                    else None)
            if code is not None:
                callbacks.append(code)
            body = b"Sketchfab authorization received. Return to ATLAS." if code else b"Sketchfab authorization unavailable."
            self.send_response(200 if code else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass

    if not _secret(oauth.client_id) or not _secret(oauth.client_secret):
        raise ValueError("Set ATLAS_SKETCHFAB_CLIENT_ID and ATLAS_SKETCHFAB_CLIENT_SECRET for browser login")
    query = urlencode({"response_type": "code", "client_id": oauth.client_id, "redirect_uri": redirect_uri, "state": state})
    with _LoopbackServer(("127.0.0.1", parts.port), Handler) as callback:
        callback.timeout = 1
        if not webbrowser.open(f"{AUTHORIZE_URL}?{query}"):
            raise ValueError("ATLAS could not open the browser for Sketchfab authorization")
        deadline = time.monotonic() + 120
        while not callbacks and time.monotonic() < deadline:
            callback.handle_request()
    if not callbacks or not callbacks[0]:
        raise ValueError("Sketchfab browser authorization was declined or timed out")
    oauth._exchange({"grant_type": "authorization_code", "code": callbacks[0], "redirect_uri": redirect_uri})


_ACTIVE_OAUTH: ContextVar[SketchfabOAuth | None] = ContextVar("sketchfab_oauth", default=None)


def sketchfab_auth_status():
    """Verify the configured user with Sketchfab and discard the profile response."""
    oauth = _ACTIVE_OAUTH.get() or SketchfabOAuth.from_environment()
    user = oauth._authorized_request(f"{API}/me")
    if not isinstance(user.get("uid"), str) or not UID.fullmatch(user["uid"]):
        raise ValueError("Sketchfab did not confirm an authenticated user")
    return {"provider": "sketchfab", "authenticated": True}


@contextmanager
def sketchfab_login():
    """Authorize this invocation in the browser and scope credentials to it."""
    oauth = SketchfabOAuth(client_id=os.environ.get("ATLAS_SKETCHFAB_CLIENT_ID", ""),
                           client_secret=os.environ.get("ATLAS_SKETCHFAB_CLIENT_SECRET", ""))
    _authorize(oauth, os.environ.get("ATLAS_SKETCHFAB_REDIRECT_URI", ""))
    context = _ACTIVE_OAUTH.set(oauth)
    try:
        yield
    finally:
        _ACTIVE_OAUTH.reset(context)


def _check_archive_url(url):
    try:
        parts = _https(url, ARCHIVE_HOST)
        if (not parts.query or not re.fullmatch(r"/archives/[a-f0-9]{32}/gltf/(?:[A-Za-z0-9_.-]{1,200}/){0,3}"
                                                r"[A-Za-z0-9_.-]{1,200}", parts.path)
                or any(segment in {".", ".."} for segment in parts.path.split("/"))):
            raise ValueError
    except ValueError:
        raise ValueError("Sketchfab archive must use the documented HTTPS download host and glTF archive path") from None


def _open_archive(url):
    _check_archive_url(url)
    return _open(Request(url, headers={"User-Agent": "ATLAS-Animation/0.5.2", "Accept-Encoding": "identity"}))


def _text(value, limit):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit and not re.search(r"[\x00-\x1f\x7f]", value)


def _slugs(items, *fields):
    if not isinstance(items, list):
        return []
    return sorted({item[field] for item in items[:100] if isinstance(item, dict) for field in fields
                   if isinstance(item.get(field), str) and SLUG.fullmatch(item[field])})


def _thumbnail(row, uid):
    container = row.get("thumbnails")
    images = container.get("images") if isinstance(container, dict) else None
    if not isinstance(images, list):
        return None
    for image in images[:12]:
        if not isinstance(image, dict) or image.get("width") not in (256, 512, 720, 1024):
            continue
        url = image.get("url")
        try:
            parts = _https(url, "media.sketchfab.com")
        except ValueError:
            continue
        if not parts.query and re.fullmatch(rf"/models/{uid}/thumbnails/[a-z0-9]+/[a-z0-9]+\.(?:png|jpeg|jpg)", parts.path):
            return url
    return None


def _license(row, *, detail=False):
    raw = row.get("license")
    if not isinstance(raw, dict):
        return None
    uid = raw.get("uid")
    if detail and isinstance(raw.get("uri"), str) and raw["uri"].startswith(API + "/licenses/"):
        uid = raw["uri"].removeprefix(API + "/licenses/")
    selected = LICENSES.get(uid) if isinstance(uid, str) else None
    if selected and detail:
        slug, _, url = selected
        if raw.get("slug") != slug or raw.get("url") not in (url, "http" + url.removeprefix("https")):
            return None
    return selected


def _model_entry(row, *, detail=False):
    if not isinstance(row, dict) or row.get("isDownloadable") is not True or row.get("isAgeRestricted") is not False:
        return None
    if (row.get("isProtected") is True or row.get("isPublished") is False or row.get("price") not in (None, 0)
            or row.get("visibility") not in (None, "public") or row.get("animationCount", 0) != 0):
        return None
    uid, name, user = (row.get(k) for k in ("uid", "name", "user"))
    selected_license = _license(row, detail=detail)
    if (not isinstance(uid, str) or not UID.fullmatch(uid) or not _text(name, 200)
            or not isinstance(user, dict) or selected_license is None):
        return None
    username = user.get("username")
    if not _text(username, 100) or not re.fullmatch(r"[A-Za-z0-9_.-]+", username):
        return None
    creator = user.get("displayName")
    creator = f"{creator.strip()} (@{username})" if _text(creator, 200) else f"@{username}"
    name = name.strip()
    source = f"https://sketchfab.com/3d-models/{uid}"
    try:
        viewer = _https(row.get("viewerUrl"), "sketchfab.com")
        if not viewer.query and re.fullmatch(rf"/3d-models/[a-z0-9_-]+-{uid}", viewer.path):
            source = row["viewerUrl"]
    except ValueError:
        pass
    revision = row.get("updatedAt") or row.get("publishedAt")
    if not _text(revision, 40):
        return None
    try:
        datetime.fromisoformat(revision)
    except ValueError:
        return None
    categories = _slugs(row.get("categories"), "slug", "name")
    tags = _slugs(row.get("tags"), "slug")
    style = "unclassified"
    if any("photogrammetry" in tag for tag in tags):
        style = "photogrammetry"
    elif set(tags) & {"low-poly", "lowpoly", "stylized"}:
        style = "stylized"
    _, license_id, license_url = selected_license
    thumbnail = _thumbnail(row, uid)
    return {"id": f"sketchfab-{uid}", "provider": "sketchfab", "uid": uid, "name": name, "creator": creator,
            "source_url": source, "license_id": license_id, "license_url": license_url, "revision": revision,
            "credit": "3D models provided by Sketchfab", "creator_username": username, "style": style,
            "category": "environment" if set(categories) & {"architecture", "nature-plants", "places-travel"} else "prop",
            "source_categories": categories, "source_tags": tags, "tags": sorted(set(tags + categories))[:100],
            "attribution": f'"{name}" by {creator}, via Sketchfab ({source}), licensed {license_id} ({license_url}).',
            **({"thumbnail_url": thumbnail} if thumbnail else {})}


def _search_filters(items):
    if (not isinstance(items, (tuple, list)) or len(items) > 5
            or any(not isinstance(item, str) or not SLUG.fullmatch(item) for item in items)):
        raise ValueError("Sketchfab search accepts up to five category or tag slugs per filter")
    return tuple(dict.fromkeys(items))


@dataclass(frozen=True)
class Sketchfab:
    id: str = "sketchfab"
    label: str = "3D models provided by Sketchfab"

    def discover(self, query=None, *, categories=(), tags=(), pages=1):
        if type(pages) is not int or not 1 <= pages <= 5:
            raise ValueError("Sketchfab search supports one to five pages per query and license")
        if query is not None and not _text(query, 200):
            raise ValueError("Sketchfab search query must contain 1–200 characters")
        categories, tags = _search_filters(categories), _search_filters(tags)
        params = {"type": "models", "downloadable": "true", "animated": "false", "count": 24,
                  "available_archive_type": "gltf", "archives_max_size": 128 * MIB}
        if categories:
            params["categories"] = ",".join(categories)
        if tags:
            params["tags"] = ",".join(tags)
        results = {}
        for term in (query.strip(),) if query else DEFAULT_QUERIES:
            for slug, license_id, _ in LICENSES.values():
                self._discover_pages(params | {"q": term, "license": slug}, results, license_id, categories, tags, pages)
        return list(results.values())

    @staticmethod
    def _discover_pages(params, results, license_id, categories, tags, pages):
        seen_cursors = set()
        for _ in range(pages):
            response = _json_request(f"{API}/search?{urlencode(params)}")
            rows = response.get("results")
            if not isinstance(rows, list) or len(rows) > 24:
                raise ValueError("Sketchfab returned an invalid search page")
            for row in rows:
                entry = _model_entry(row)
                if (entry and entry["license_id"] == license_id
                        and set(categories).issubset(entry["source_categories"])
                        and set(tags).issubset(entry["source_tags"])):
                    archives = row.get("archives")
                    gltf = archives.get("gltf") if isinstance(archives, dict) else None
                    size = gltf.get("size") if isinstance(gltf, dict) else None
                    if type(size) is int and 0 < size <= 128 * MIB:
                        for source, key in (("faceCount", "face_count"), ("vertexCount", "vertex_count"),
                                            ("textureCount", "texture_count"), ("textureMaxResolution", "texture_resolution")):
                            value = gltf.get(source)
                            if type(value) is int and 0 <= value <= 2**31 - 1:
                                entry[key] = value
                        results.setdefault(entry["id"], entry | {"source_bytes": size,
                                                                "staff_picked": bool(row.get("staffpickedAt"))})
            cursors = response.get("cursors")
            cursor = cursors.get("next") if isinstance(cursors, dict) else None
            if not isinstance(cursor, str) or not re.fullmatch(r"[A-Za-z0-9+/_=-]{1,512}", cursor) or cursor in seen_cursors:
                break
            seen_cursors.add(cursor)
            params["cursor"] = cursor

    def acquire(self, entry, cache, library, budget, *, resolution="1k", source_format=None):
        if resolution != "1k" or source_format not in (None, "gltf"):
            raise ValueError("Sketchfab acquisition uses the glTF ZIP with provider-selected textures")
        if type(budget) is not int or not 1 <= budget <= 512 * MIB:
            raise ValueError("Sketchfab download budget must be 1 byte to 512 MiB with a 128 MiB archive cap")
        uid = entry.get("uid")
        if not isinstance(uid, str) or not UID.fullmatch(uid) or entry.get("id") != f"sketchfab-{uid}":
            raise ValueError("Invalid Sketchfab asset identity")
        model = _model_entry(_json_request(f"{API}/models/{uid}"), detail=True)
        if not model or model["uid"] != uid or model["license_id"] != entry.get("license_id"):
            raise ValueError("Sketchfab model or supported license changed. Synchronize the catalog and review the source.")
        oauth = _ACTIVE_OAUTH.get() or SketchfabOAuth.from_environment()
        archive_path, transfer = self._download_archive(model, oauth, cache, min(budget, 128 * MIB))
        try:
            with ZipFile(archive_path) as archive:
                members = unpack_models(archive)
                body = archive_model(archive, members, "scene.gltf", texture_subdirectory=True)
        except BadZipFile:
            raise ValueError("Sketchfab glTF source is not a valid ZIP archive") from None
        license_text = fetch_bytes(model["license_url"] + "legalcode.txt", limit=MIB).decode("utf-8")
        if "Creative Commons" not in license_text:
            raise ValueError("Sketchfab's Creative Commons license text could not be verified")
        provenance = Provenance(name=model["name"], creator=model["creator"], source_url=model["source_url"],
            license_id=model["license_id"], license_text=license_text, approval="approved", render_allowed=True,
            redistribution_allowed=True, category=model["category"], tags=model["tags"],
            attribution=model["attribution"] + " Converted from the Sketchfab glTF archive to embedded GLB.",
            description=f"Source revision {model['revision']}. Source ZIP SHA256 {transfer['sha256']}.")
        provenance.require_render_rights()
        with tempfile.TemporaryDirectory(prefix="atlas-sketchfab-") as temp:
            source = Path(temp) / "model.glb"
            source.write_bytes(body)
            record = AssetRegistry(library).register(source, model["id"], provenance)
        return {"catalog": model, "download": transfer, "asset": record, "source_format": "gltf",
                "status": "registered-glb"}

    @staticmethod
    def _download_archive(model, oauth, cache, budget):
        for attempt in range(2):
            ticket = oauth.download_ticket(model["uid"]).get("gltf")
            if not isinstance(ticket, dict) or type(ticket.get("expires")) is not int or ticket["expires"] <= 0:
                raise ValueError("Sketchfab did not issue a current glTF archive link")
            url, size = ticket.get("url"), ticket.get("size")
            _check_archive_url(url)
            if type(size) is not int or not 0 < size <= budget:
                raise ValueError("Sketchfab archive size is missing or exceeds the download budget")
            identity = f"{model['id']}:{model['revision']}:{urlsplit(url).path}"
            try:
                return download(url, cache, budget, expected_size=size, cache_key=identity,
                                recorded_url=model["source_url"], validate_url=_check_archive_url, open_url=_open_archive)
            except HTTPError as exc:
                exc.close()
                if attempt or exc.code != 403:
                    raise SketchfabAPIError(exc.code) from None
            except (URLError, TimeoutError, ConnectionError, HTTPException):
                raise ValueError("Sketchfab archive transfer failed") from None
        raise ValueError("Sketchfab archive access could not be renewed")
