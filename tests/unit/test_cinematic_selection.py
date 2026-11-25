from engine.assets.providers import store_catalog


def test_deterministic_selection_reports_unverified_history_and_discovery(tmp_path):
    from engine.assets.selection import AssetRequirements, select_assets

    cache, library = tmp_path / "cache", tmp_path / "library"
    fields = {"provider": "polyhaven", "category": "environment", "style": "photorealistic",
              "category_path": "Architecture/Facades/Fortifications", "tags": ["stone", "castle"],
              "license_id": "CC0-1.0"}
    store_catalog("polyhaven", cache, [fields | {"id": f"polyhaven-castle_{i}", "name": f"Fort {i}"}
                                     for i in range(3)], "Poly Haven", replace=True)
    requirement = AssetRequirements(category="architecture", subcategory="castle", style="realistic",
                                    require_ready=False, preferred_providers=["polyhaven"])
    first = select_assets(requirement, cache, library, seed=17)
    assert first == select_assets(requirement, cache, library, seed=17)
    assert len(first["candidates"]) == 3
    assert all(item["status"] == "discovered" and item["pin"] is None for item in first["candidates"])
    strict = requirement.model_copy(update={"require_ready": True, "historical_period": "medieval"})
    output = select_assets(strict, cache, library)
    assert not output["candidates"]
    assert all("history" in item["reasons"] and "inspection" in item["reasons"] for item in output["rejected"])
