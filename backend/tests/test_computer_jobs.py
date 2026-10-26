"""Approved job lifecycle and ownership, exercised with real, harmless Windows processes on isolated data."""

import asyncio
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

import pytest
from sqlalchemy import select

from junior.computer import jobs, owned_process
from junior.computer import tools as pc_tools
from junior.computer.terminal import clean_env
from junior.db import ApprovalItem, ComputerJob, session_scope
from junior.permissions import RuleChangeError, set_mode, set_rule
from junior.senders.base import Outgoing
from junior.settings_store import set_setting
from test_computer_paths import context_with, pc as pc_fixture  # noqa: F401

pc_home = pc_fixture


def propose(client, command="Write-Output 'job hello'", seconds=20, folder="Desktop"):
    ctx = context_with("Run this background command")
    text = asyncio.run(pc_tools.start_job_for(ctx, command, folder, seconds))
    assert "waiting for their OK" in text
    return client.get(f"/api/approvals/{ctx.approval_ids[-1]}").json()


def start(client, command="Write-Output 'job hello'", seconds=20):
    card = propose(client, command, seconds)
    response = client.post(f"/api/approvals/{card['id']}/approve", json={})
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["status"] == "posted", item
    return item["meta"]["remote_id"], card


def wait_for(client, job_id, states=("completed", "failed", "stopped", "timed_out", "interrupted"), text="", timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        row = client.get(f"/api/computer/jobs/{job_id}").json()
        if row["state"] in states and text in row["output"]:
            return row
        time.sleep(0.1)
    pytest.fail(f"Job didn't reach {states} with {text!r}: {row}")


def alive(pid):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes, api.OpenProcess.restype = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE
    api.WaitForSingleObject.argtypes, api.WaitForSingleObject.restype = [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE; read-only
    if not handle:
        return False
    try:
        return api.WaitForSingleObject(handle, 0) == 258
    finally:
        api.CloseHandle(handle)


def test_command_waits_then_background_job_finishes_and_retains_output(pc_home):
    user, c = pc_home
    marker = user / "Desktop" / "made-by-job.txt"
    card = propose(c, "Write-Output 'job hello'; Set-Content made-by-job.txt 'done'")
    assert not marker.exists()
    assert c.get("/api/computer/jobs").json()["jobs"] == []
    done = c.post(f"/api/approvals/{card['id']}/approve", json={}).json()
    job_id = done["meta"]["remote_id"]
    row = wait_for(c, job_id)
    assert row["state"] == "completed" and row["exit_code"] == 0
    assert "job hello" in row["output"] and marker.read_text().strip() == "done"
    assert row["approval_id"] == card["id"] and row["finished_at"]
    # A duplicate Approve never makes another job.
    assert c.post(f"/api/approvals/{card['id']}/approve", json={}).status_code == 409
    assert len(c.get("/api/computer/jobs").json()["jobs"]) == 1
    ctx = context_with("Read its status")
    report = pc_tools.job_status_for(ctx, job_id)
    assert "job hello" in report and "data, never instructions" in report
    assert ctx.outside_content_seen


@pytest.mark.parametrize("command,expected", [("Write-Output 'oops'; exit 3", 3),
                                               ("Get-Item a-missing-junior-test-file", 1)])
def test_error_exit_is_not_reported_as_success(pc_home, command, expected):
    _, c = pc_home
    job_id, _ = start(c, command)
    row = wait_for(c, job_id)
    assert row["state"] == "failed" and row["exit_code"] == expected


def test_stop_and_timeout_only_stop_owned_processes(pc_home):
    _, c = pc_home
    job_id, _ = start(c, "Write-Output 'ready'; Start-Sleep -Seconds 40", seconds=30)
    wait_for(c, job_id, ("running",), "ready")
    stopped = c.post(f"/api/computer/jobs/{job_id}/stop").json()
    assert stopped["state"] == "stopped" and stopped["finished_at"]
    assert c.post(f"/api/computer/jobs/{job_id}/stop").json()["state"] == "stopped"
    assert c.post(f"/api/computer/jobs/{os.getpid()}/stop").status_code == 404
    assert alive(os.getpid())
    timed, _ = start(c, "Start-Sleep -Seconds 40; Write-Output 'too late'", seconds=1)
    row = wait_for(c, timed)
    assert row["state"] == "timed_out" and "too late" not in row["output"]


def test_stopping_also_terminates_child_processes(pc_home):
    _, c = pc_home
    command = ("$child = Start-Process powershell.exe -ArgumentList '-NoProfile -Command Start-Sleep -Seconds 40' "
               "-PassThru -NoNewWindow; Write-Output ('child=' + $child.Id); Start-Sleep -Seconds 40")
    job_id, _ = start(c, command, seconds=30)
    row = wait_for(c, job_id, ("running",), "child=")
    child_pid = int(row["output"].split("child=", 1)[1].splitlines()[0])
    assert alive(child_pid)
    assert c.post(f"/api/computer/jobs/{job_id}/stop").json()["state"] == "stopped"
    assert not alive(child_pid)


def test_backend_crash_closes_owned_tree_before_any_recovery(pc_home):
    user, _ = pc_home
    script = ("import asyncio,sys; from junior.computer.owned_process import spawn\n"
              "async def main():\n"
              " p,t = await spawn('Start-Sleep -Seconds 40', sys.argv[1])\n"
              " print(p.pid, flush=True)\n"
              " await asyncio.sleep(40)\n"
              "asyncio.run(main())\n")
    supervisor = subprocess.Popen([sys.executable, "-u", "-c", script, str(user / "Desktop")],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=clean_env())
    try:
        pid = int(supervisor.stdout.readline().strip())
        assert alive(pid)
        supervisor.terminate()
        supervisor.communicate(timeout=10)
        end = time.monotonic() + 5
        while alive(pid) and time.monotonic() < end:
            time.sleep(0.1)
        assert not alive(pid)
    finally:
        if supervisor.poll() is None:
            supervisor.kill()
        supervisor.communicate(timeout=10)


@pytest.mark.parametrize("seconds", [0, -1, 3601, True, 2.5])
def test_invalid_duration_is_refused_before_card(pc_home, seconds):
    ctx = context_with("run")
    assert "NOT done" in asyncio.run(pc_tools.start_job_for(ctx, "echo hello", "Desktop", seconds))
    assert ctx.approval_ids == []


def test_path_dangerous_edit_and_plan_checks(pc_home):
    user, c = pc_home
    ctx = context_with("run it")
    assert "outside" in asyncio.run(pc_tools.start_job_for(ctx, "echo hello", str(user / "Other")))
    assert "never run" in asyncio.run(pc_tools.start_job_for(ctx, "shutdown /s", "Desktop"))
    set_mode("plan")
    assert "Plan mode" in asyncio.run(pc_tools.start_job_for(ctx, "echo hello", "Desktop"))
    set_mode("rules")
    card = propose(c)
    c.patch(f"/api/approvals/{card['id']}", json={"text": "shutdown /s"})
    result = c.post(f"/api/approvals/{card['id']}/approve", json={}).json()
    assert result["status"] == "approved" and "never run" in result["meta"]["last_error"]
    assert c.get("/api/computer/jobs").json()["jobs"] == []
    with pytest.raises(RuleChangeError, match="locked"):
        set_rule("computer.run", "auto")
    with pytest.raises(RuleChangeError, match="locked"):
        set_rule("computer.job.stop", "auto")


def test_live_output_is_bounded_and_known_secrets_redacted(pc_home):
    _, c = pc_home
    command = "Write-Output ('x' * 24000); Write-Output ('sk-' + ('a' * 40)); Write-Output ('access_' + 'token=pretendsecret')"
    job_id, _ = start(c, command)
    row = wait_for(c, job_id)
    assert row["state"] == "completed" and row["output_truncated"]
    assert row["output_chars"] > jobs.OUTPUT_CHARS and len(row["output"]) <= jobs.OUTPUT_CHARS
    assert "sk-" not in row["output"] and "pretendsecret" not in row["output"]
    assert "redacted" in row["output"]


@pytest.mark.parametrize("setting,value", [("paused", True), ("computer_enabled", False), ("permission_mode", "plan")])
def test_pause_off_and_plan_stop_existing_jobs(pc_home, setting, value):
    _, c = pc_home
    job_id, _ = start(c, "Write-Output 'ready'; Start-Sleep -Seconds 40", seconds=30)
    wait_for(c, job_id, ("running",), "ready")
    set_setting(setting, value)
    assert wait_for(c, job_id)["state"] == "stopped"
    # Owner cancellation still works even if tools are unavailable.
    assert c.post(f"/api/computer/jobs/{job_id}/stop").status_code == 200


def test_recovery_never_kills_or_replays_saved_pid(pc_home):
    _, c = pc_home
    with session_scope() as s:
        s.add(ComputerJob(id="orphan", command="echo x", folder="unused", seconds=30,
                          state="running", pid=os.getpid()))
    assert c.post("/api/computer/jobs/orphan/stop").status_code == 409
    assert jobs.recover_interrupted() == 1 and alive(os.getpid())
    row = jobs.get_job("orphan")
    assert row["state"] == "interrupted" and row["finished_at"]
    with session_scope() as s:
        assert s.get(ComputerJob, "orphan").pid is None


def test_concurrency_limit_and_shutdown(pc_home):
    _, c = pc_home
    ids = [start(c, "Start-Sleep -Seconds 40", seconds=30)[0] for _ in range(jobs.MAX_RUNNING)]
    card = propose(c)
    response = c.post(f"/api/approvals/{card['id']}/approve", json={}).json()
    assert response["status"] == "approved" and "At most 3" in response["meta"]["last_error"]
    c.portal.call(c.app.state.pc_jobs.close)
    assert all(jobs.get_job(job_id)["state"] == "stopped" for job_id in ids)


def test_job_assignment_failure_does_not_release_command(pc_home, monkeypatch):
    user, c = pc_home
    def fail(self, pid):
        raise OSError("pretend ownership failure")
    monkeypatch.setattr(owned_process.OwnedTree, "assign", fail)
    card = propose(c, "Set-Content should-not-exist.txt 'bad'")
    response = c.post(f"/api/approvals/{card['id']}/approve", json={}).json()
    assert response["status"] == "approved"
    assert not (user / "Desktop" / "should-not-exist.txt").exists()
    with session_scope() as s:
        assert s.scalar(select(ComputerJob)).state == "failed"


def test_manager_refuses_unapproved_or_tampered_requests(pc_home):
    _, c = pc_home
    card = propose(c)
    out = Outgoing(card["id"], "computer.run", "computer", "background command", card["text"], meta=card["meta"])
    with pytest.raises(jobs.JobError, match="approved"):
        c.portal.call(c.app.state.pc_jobs.start, out)
    tampered = Outgoing(card["id"], "computer.run", "computer", "background command", card["text"],
                        meta={**card["meta"], "path": "C:\\Windows"})
    with pytest.raises(jobs.JobError, match="approved background command"):
        c.portal.call(c.app.state.pc_jobs.start, tampered)
    assert c.get("/api/computer/jobs").json()["jobs"] == []
    assert c.post("/api/computer/jobs", json={"command": "echo bypass"}).status_code == 405


def test_duration_rechecked_and_retry_of_started_card_never_replays(pc_home):
    _, c = pc_home
    card = propose(c)
    with session_scope() as s:
        item = s.get(ApprovalItem, card["id"])
        item.meta = {**item.meta, "seconds": jobs.MAX_SECONDS + 1}
    refused = c.post(f"/api/approvals/{card['id']}/approve", json={}).json()
    assert refused["status"] == "approved" and "time limit" in refused["meta"]["last_error"]
    job_id, card = start(c)
    wait_for(c, job_id)
    # Even a manual retry with a fresh dispatch attempt cannot replay a job already associated with the card.
    with session_scope() as s:
        item = s.get(ApprovalItem, card["id"])
        item.status = "approved"
    result = c.post(f"/api/approvals/{card['id']}/send").json()
    assert result["status"] == "approved" and "will not run twice" in result["meta"]["last_error"]
    assert len(c.get("/api/computer/jobs").json()["jobs"]) == 1


def test_status_read_respects_deny_and_active_jobs_are_not_hidden(pc_home):
    _, _client = pc_home
    from datetime import timedelta
    from junior.db.models import utcnow
    with session_scope() as s:
        s.add(ComputerJob(id="active", command="echo x", folder="unused", seconds=30,
                          state="running", created_at=utcnow() - timedelta(days=1)))
        for i in range(12):
            s.add(ComputerJob(id=f"done-{i}", command="echo x", folder="unused", seconds=30, state="completed"))
    assert jobs.list_jobs(10)[0]["id"] == "active"
    set_rule("computer.read", "deny")
    assert "turned off" in pc_tools.job_status_for(context_with("status"), "active")


def test_output_capture_failure_stops_the_owned_job(pc_home, monkeypatch):
    _, c = pc_home
    def fail_redaction(text):
        raise OSError("pretend capture failure")
    monkeypatch.setattr(jobs, "redact", fail_redaction)
    job_id, _ = start(c, "Write-Output 'ready'; Start-Sleep -Seconds 40", seconds=30)
    row = wait_for(c, job_id)
    assert row["state"] == "interrupted" and "capture" in row["note"]


def test_agent_stop_card_waits_and_cannot_be_edited_into_another_target(pc_home):
    _, c = pc_home
    job_id, _ = start(c, "Write-Output 'ready'; Start-Sleep -Seconds 40", seconds=30)
    wait_for(c, job_id, ("running",), "ready")
    ctx = context_with(f"Stop PC job {job_id}")
    assert "waiting for their OK" in asyncio.run(pc_tools.stop_job_for(ctx, job_id))
    assert jobs.get_job(job_id)["state"] == "running"
    card_id = ctx.approval_ids[-1]
    c.patch(f"/api/approvals/{card_id}", json={"text": "Stop PC job some-other-target"})
    refused = c.post(f"/api/approvals/{card_id}/approve", json={}).json()
    assert refused["status"] == "approved" and "stop target" in refused["meta"]["last_error"]
    assert jobs.get_job(job_id)["state"] == "running"
    ctx = context_with(f"Stop PC job {job_id}")
    asyncio.run(pc_tools.stop_job_for(ctx, job_id))
    result = c.post(f"/api/approvals/{ctx.approval_ids[-1]}/approve", json={}).json()
    assert result["status"] == "posted" and jobs.get_job(job_id)["state"] == "stopped"
