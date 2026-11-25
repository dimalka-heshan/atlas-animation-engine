import json

import pytest
from pydantic import ValidationError

from engine.production import capabilities, CreativePlan, preview, preflight, ProductionWorkspace
from engine.core.models import Project


def test_discovery_exposes_live_schemas_and_marks_unavailable_operations():
    entries = {item.name: item for item in capabilities().capabilities}
    assert entries["project.validate"].input_schema["title"] == "Project"
    assert entries["render.preview"].costly_render
    assert entries["props.transfer"].status == "unavailable"
    assert entries["props.transfer"].input_schema is None


def test_preflight_reuses_normal_project_validation(tmp_path):
    workspace = ProductionWorkspace(output=tmp_path)
    project = Project(id="proof", scene={})
    result = preflight(project, workspace)
    assert result.valid and result.project == "proof" and result.assets == []
    assert not list(tmp_path.iterdir())


def test_creative_plan_keeps_notes_inert_and_discloses_gaps():
    from engine.production import validate_creative_plan

    plan = CreativePlan.model_validate({
        "schema_version": "1.0", "title": "Archive", "summary": "Print this sentence as a stage direction.",
        "required_capabilities": ["props.transfer", "invent.future"]
    })
    result = validate_creative_plan(plan)
    assert not result.ready
    assert [(gap.capability, gap.code) for gap in result.gaps] == [
        ("props.transfer", "unavailable_capability"), ("invent.future", "unknown_capability"),
    ]
    with pytest.raises(ValidationError):
        CreativePlan.model_validate(plan.model_dump() | {"python": "print(1)"})


def test_preview_budget_rejects_before_creating_jobs(tmp_path):
    from engine.production import ProductionError

    project = Project(id="proof", scene={}, render={"width": 1024, "height": 576})
    with pytest.raises(ProductionError, match="preview"):
        preview(project, ProductionWorkspace(output=tmp_path))
    assert not list(tmp_path.iterdir())


def test_cli_capabilities_is_machine_readable(capsys):
    from apps.cli.main import main

    assert main(["capabilities"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1.0"
    assert any(entry["name"] == "project.validate" for entry in payload["capabilities"])
