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
