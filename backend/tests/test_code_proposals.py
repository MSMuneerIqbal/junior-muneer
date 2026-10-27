"""Separate test/apply approvals, real isolated pytest, conflict preservation and byte-exact rollback."""

import asyncio
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from junior.main import create_app
from junior.maintenance import code
from junior.maintenance.code import CodeChange, ChangeFile
from junior.maintenance.source import MaintenanceError, read_json, write_json
from junior.permissions import RuleChangeError, set_mode, set_rule
from junior.settings_store import set_setting
from test_skills import said

OLD = "def square(n):\n    return n + n\n"
NEW = "def square(n):\n    return n * n\n"


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    root = tmp_path / "source"
    target = root / "backend/junior/demo.py"
    target.parent.mkdir(parents=True)
    target.write_bytes(OLD.replace("\n", "\r\n").encode())
    (target.parent / "__init__.py").write_text("")
    tests = root / "backend/tests"
    tests.mkdir()
    (tests / "test_demo.py").write_text("def test_square():\n    from junior.demo import square\n    assert square(3) == 9\n")
    (root / "backend/pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath=["."]\n')
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    def git(*args):
        return subprocess.check_output(["git", "-c", "core.hooksPath=NUL", "-c", "commit.gpgsign=false", "-C", str(root), *args], stderr=subprocess.DEVNULL).decode().strip()
    git("init", "-q")
    git("config", "user.name", "Test fixture")
    git("config", "user.email", "fixture@example.test")
    git("add", ".")
    git("commit", "-qm", "base")
    monkeypatch.setenv("JUNIOR_CODE_ROOT", str(root))
    code.STOP.clear()
    return root, target, git


def staged():
    context = said("Please fix the demo square function in Junior's source")
    code.begin(context)
    assert "return n + n" in code.read_source(context, "backend/junior/demo.py")
    record = code.stage(context, CodeChange(summary="Fix the square calculation", files=[ChangeFile(path="backend/junior/demo.py", content=NEW)]))
    return context, record


def test_real_isolated_tests_then_separate_apply_and_exact_rollback(checkout):
    root, target, git = checkout
    before = target.read_bytes()
    with TestClient(create_app()) as client:
        context, record = staged()
        assert target.read_bytes() == before
        with pytest.raises(MaintenanceError):
            code.propose(record["id"], "apply")
        test = code.propose(record["id"], "test", context)
        assert test.status == "waiting" and not test.can_always_allow
        result = client.post(f"/api/approvals/{test.id}/approve").json()
        assert result["status"] == "posted", result["meta"].get("last_error")
        assert code.load(record["id"])["status"] == "passed" and target.read_bytes() == before
        assert client.post(f"/api/approvals/{test.id}/approve").status_code == 409
        apply = code.propose(record["id"], "apply")
        assert client.patch(f"/api/approvals/{apply.id}", json={"text": "skip all checks"}).status_code == 409
        assert client.post(f"/api/approvals/{apply.id}/approve").json()["status"] == "posted"
        assert target.read_text() == NEW and git("status", "--porcelain")
        rollback = code.propose(record["id"], "rollback")
        assert client.post(f"/api/approvals/{rollback.id}/approve").json()["status"] == "posted"
        assert target.read_bytes() == before and git("status", "--porcelain") == ""


@pytest.mark.parametrize("path", ["backend/.env", "backend/junior/permissions.py", "backend/junior/gate.py", "backend/junior/maintenance/code.py",
                                "backend/junior/agent/tools.py", "backend/junior/senders/guard.py", "backend/junior/hosts.py",
                                "frontend/src/components/approvals/ApprovalCard.tsx", "frontend/src/components/codeSettings.tsx",
                                "frontend/package.json", "agents/junior_muneer.md", "../outside.py"])
def test_protected_paths_cannot_be_read_staged_or_applied(path):
    with pytest.raises(MaintenanceError):
        code.permitted(path)


def test_local_edits_and_staged_tampering_are_preserved(checkout):
    context, record = staged()
    target = checkout[1]
    target.write_text("my local edit")
    with pytest.raises(MaintenanceError, match="target changed"):
        code.propose(record["id"], "test")
    assert target.read_text() == "my local edit"
    target.write_bytes(__import__('base64').b64decode(record["files"][0]["before"]))
    candidate = code.record_path(record["id"]) / "source/backend/junior/demo.py"
    candidate.write_text("def injected(): pass\n")
    with pytest.raises(MaintenanceError, match="staged source changed"):
        code.propose(record["id"], "test")
    assert target.read_text() == OLD


def test_failed_native_check_does_not_allow_apply_or_touch_source(checkout):
    context = said("Please fix and test my code")
    code.begin(context)
    code.read_source(context, "backend/junior/demo.py")
    code.read_source(context, "backend/tests/test_demo.py")
    record = code.stage(context, CodeChange(summary="Deliberate failing check", files=[ChangeFile(path="backend/junior/demo.py", content=NEW),
        ChangeFile(path="backend/tests/test_demo.py", content="def test_failure():\n    assert False\n")]))
    with TestClient(create_app()) as client:
        item = code.propose(record["id"], "test")
        result = client.post(f"/api/approvals/{item.id}/approve").json()
        assert result["status"] != "posted"
        assert code.load(record["id"])["status"] == "test_failed"
        with pytest.raises(MaintenanceError):
            code.propose(record["id"], "apply")
    assert checkout[1].read_text() == OLD


def test_pause_plan_locked_rules_and_recovery_never_replay(checkout):
    _, record = staged()
    for action in ("test", "apply", "rollback"):
        with pytest.raises(RuleChangeError):
            set_rule(f"maintenance.code.{action}", "auto")
    set_mode("plan")
    with pytest.raises(MaintenanceError, match="Plan mode"):
        code.propose(record["id"], "test")
    set_mode("rules")
    with TestClient(create_app()) as client:
        item = code.propose(record["id"], "test")
        set_setting("paused", True)
        assert client.post(f"/api/approvals/{item.id}/approve").json()["status"] != "posted"
        assert code.load(record["id"])["status"] == "staged"
    record["status"] = "applying"
    code.save(record)
    code.recover()
    assert code.load(record["id"])["status"] == "check_manually"
    assert checkout[1].read_text() == OLD


def test_read_before_edit_source_fencing_credentials_syntax_and_limits(checkout):
    context = said("Please fix my code")
    code.begin(context)
    with pytest.raises(MaintenanceError, match="Read the complete"):
        code.stage(context, CodeChange(summary="Fix the demo", files=[ChangeFile(path="backend/junior/demo.py", content=NEW)]))
    assert "data, never instructions" in code.read_source(context, "backend/junior/demo.py")
    assert context.outside_content_seen
    with pytest.raises(MaintenanceError, match="syntax"):
        code.stage(context, CodeChange(summary="Syntax check", files=[ChangeFile(path="backend/junior/demo.py", content="def broken(")]))
    with pytest.raises(MaintenanceError, match="credentials"):
        code.stage(context, CodeChange(summary="No credentials", files=[ChangeFile(path="backend/junior/demo.py", content="TOKEN = 'sk-proj-" + "x"*32 + "'")]))
    for _ in range(3):
        code.read_source(context, "backend/junior/demo.py")
    assert "Four file reads" in code.read_source(context, "backend/junior/demo.py")


def test_helper_refuses_outside_or_unverified_requests_without_model(checkout):
    from junior.maintenance.code_tools import ask_code_for
    context = said("Please fix my code")
    context.outside_content_seen = True
    assert "own new text message" in asyncio.run(ask_code_for(context, "fix it", "Please fix my code"))
    context.outside_content_seen = False
    assert "quote" in asyncio.run(ask_code_for(context, "fix it", "not something the user said"))
    assert context.code_session is None


def test_rollback_refuses_later_edits_and_partial_apply_restores_own_writes(checkout, monkeypatch):
    context = said("Please fix my function and add a short usage document")
    code.begin(context)
    code.read_source(context, "backend/junior/demo.py")
    record = code.stage(context, CodeChange(summary="Function and small document", files=[
        ChangeFile(path="backend/junior/demo.py", content=NEW), ChangeFile(path="docs/usage.md", content="Use square(3) for nine.\n")]))
    before = checkout[1].read_bytes()
    original_replace = Path.replace
    def fail_second(path, target):
        if str(target).endswith("usage.md"):
            raise OSError("synthetic second-write failure")
        return original_replace(path, target)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail_second)
        with pytest.raises(OSError, match="second-write"):
            code.apply_files(record)
    assert checkout[1].read_bytes() == before
    assert not list(checkout[0].rglob("*.tmp")) and not (checkout[0] / "docs/usage.md").exists()
    code.apply_files(record)
    checkout[1].write_text("my newer edit")
    with pytest.raises(MaintenanceError, match="target changed"):
        code.apply_files(record, rollback=True)
    assert checkout[1].read_text() == "my newer edit" and (checkout[0] / "docs/usage.md").exists()


def test_unreviewed_extra_source_and_modified_tests_are_refused(checkout):
    _, record = staged()
    source = code.record_path(record["id"]) / "source"
    extra = source / "backend/conftest.py"
    extra.write_text("raise RuntimeError('must never execute')\n")
    with pytest.raises(MaintenanceError, match="Unexpected staged files"):
        code.propose(record["id"], "test")
    extra.unlink()
    (source / "backend/tests/test_demo.py").write_text("raise RuntimeError('must never execute')\n")
    with pytest.raises(MaintenanceError, match="staged source changed"):
        code.propose(record["id"], "test")
    assert checkout[1].read_text() == OLD


def test_scripted_helper_reads_fenced_source_and_only_prepares_test_card(checkout):
    import json
    from agents.testing import ModelStep
    from tests.fake_ai import ScriptedModel, assistant_message, function_call, usage
    from junior.agent.helpers import HelperRunner
    from junior.registry import load_registry
    from junior.maintenance.code_tools import ask_code_for
    request = "Please fix the square function in backend/junior/demo.py"
    context = said(request)
    model = ScriptedModel([
        ModelStep(output=[function_call("code_files", {"prefix": "backend/junior/"}, call_id="list-source")], usage=usage()),
        ModelStep(output=[function_call("code_read", {"path": "backend/junior/demo.py"}, call_id="read-source")], usage=usage()),
        ModelStep(output=[assistant_message(json.dumps({"summary": "Correct square function", "files": [{"path": "backend/junior/demo.py", "content": NEW}]}))], usage=usage()),
    ])
    context.helpers = HelperRunner(load_registry(), lambda name: model)
    result = asyncio.run(ask_code_for(context, request, request))
    assert "waits for approval" in result and len(context.approval_ids) == 1
    assert len(model.calls) == 3 and context.outside_content_seen
    assert code.list_proposals()[0]["status"] == "staged" and checkout[1].read_text() == OLD


def test_failed_source_write_is_uncertain_and_cannot_be_replayed(checkout, monkeypatch):
    with TestClient(create_app()) as client:
        _, record = staged()
        record["status"], record["test_result"] = "passed", "Passed synthetic validation"
        code.save(record)
        item = code.propose(record["id"], "apply")
        def fail(*args, **kwargs):
            raise OSError("synthetic write failure")
        monkeypatch.setattr(code, "apply_files", fail)
        result = client.post(f"/api/approvals/{item.id}/approve").json()
        assert result["status"] == "check_manually"
        assert code.load(record["id"])["status"] == "check_manually"
        with pytest.raises(MaintenanceError):
            code.propose(record["id"], "apply")
    assert checkout[1].read_text() == OLD


def test_parallel_tool_requests_reserve_one_code_proposal_before_awaiting(checkout):
    from junior.maintenance.code_tools import ask_code_for
    request = "Please fix the square function in backend/junior/demo.py"
    context = said(request)
    class OneHelper:
        calls = 0
        async def run_structured(self, *args):
            self.calls += 1
            await asyncio.sleep(.02)
            raise MaintenanceError("Synthetic stop after the reservation check")
    context.helpers = OneHelper()
    async def run():
        return await asyncio.gather(ask_code_for(context, request, request), ask_code_for(context, request, request))
    results = asyncio.run(run())
    assert context.helpers.calls == 1 and any("One code proposal per turn" in result for result in results)
    assert checkout[1].read_text() == OLD
