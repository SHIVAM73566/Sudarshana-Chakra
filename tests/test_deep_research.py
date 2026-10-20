"""Tests for the Autonomous Deep Research subroutine.

Web access is mocked so the tests are hermetic and never hit the network.
"""

from unittest.mock import patch

from core import deep_research as dr


def test_decompose_returns_subtasks():
    subs = dr.DeepResearch.decompose("automate supplier invoice reconciliation for manufacturing")
    assert len(subs) == 5
    assert all(isinstance(s, str) and s for s in subs)


def test_decompose_empty_goal():
    assert dr.DeepResearch.decompose("") == []


def test_run_collects_evidence_and_strategy():
    with patch.object(dr.DeepResearch, "_web_evidence", return_value="Use pandas and validate totals."):
        result = dr.DeepResearch.run("automate invoice reconciliation")
    assert result["success"]
    assert result["strategy"]
    assert len(result["subtasks"]) == 5
    assert result["web_evidence"]


def test_run_never_raises_without_web():
    with patch.object(dr.DeepResearch, "_web_evidence", return_value=""):
        result = dr.DeepResearch.run("unknown domain X")
    assert result["success"]
    assert result["strategy"]


def test_execute_contract():
    with patch.object(dr.DeepResearch, "_web_evidence", return_value="e"):
        result = dr.execute(parameters={"goal": "some unknown task"})
    assert result["success"]


def test_execute_empty_goal():
    result = dr.execute(parameters={})
    assert result["success"] is False


def test_forge_delegation():
    with patch.object(dr.DeepResearch, "_web_evidence", return_value="e"):
        with patch.object(dr.DeepResearch, "_maybe_forge", return_value={"success": True, "name": "auto_skill"}):
            result = dr.DeepResearch.run("build custom capability", allow_forge=True)
    assert result["forged_skill"]["name"] == "auto_skill"


def test_feature_metadata_schema():
    meta = dr.FEATURE_METADATA
    assert meta["name"] == "deep_research"
    params = meta["parameters"]
    assert params["type"] == "OBJECT"
    assert isinstance(params["properties"], dict)
