"""Planned posts (P2-11): pick a time, get reminded then."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from junior.approvals import create_item, remind_due
from junior.db import ApprovalItem, session_scope
from junior.db.models import utcnow
from junior.main import create_app
from junior.pause import set_paused


@pytest.fixture
def client():
    with TestClient(create_app(model_provider=lambda: (lambda n: None))) as c:
        yield c


def iso(delta: timedelta) -> str:
    return (utcnow() + delta).isoformat()


def move_back_in_time(item_id: int) -> None:
    """Pretend the planned time has come."""
    with session_scope() as s:
        s.get(ApprovalItem, item_id).planned_at = utcnow() - timedelta(minutes=1)


def test_plan_change_and_clear(client):
    item = create_item(kind="copy", platform="linkedin", item_type="post", text="Hello")
    planned = client.put(f"/api/approvals/{item.id}/plan", json={"planned_at": iso(timedelta(days=2))}).json()
    assert planned["planned_at"] and planned["due"] is False

    listed = client.get("/api/approvals?status=all&planned=true").json()
    assert [i["id"] for i in listed] == [item.id]

    cleared = client.put(f"/api/approvals/{item.id}/plan", json={"planned_at": None}).json()
    assert cleared["planned_at"] is None
    assert client.get("/api/approvals?status=all&planned=true").json() == []
    names = [a["name"] for a in client.get("/api/activity?kind=action").json()]
    assert "approval_planned" in names and "approval_unplanned" in names


def test_bad_plans_are_refused(client):
    item = create_item(kind="copy", platform="linkedin", item_type="post", text="Hello")
    r = client.put(f"/api/approvals/{item.id}/plan", json={"planned_at": iso(-timedelta(hours=1))})
    assert r.status_code == 409 and "already passed" in r.json()["detail"]
    r = client.put(f"/api/approvals/{item.id}/plan", json={"planned_at": "2030-01-01T09:00:00"})
    assert r.status_code == 409 and "time zone" in r.json()["detail"]
    client.post(f"/api/approvals/{item.id}/posted")
    r = client.put(f"/api/approvals/{item.id}/plan", json={"planned_at": iso(timedelta(days=1))})
    assert r.status_code == 409 and "only waiting or approved" in r.json()["detail"]


def test_the_scheduler_reminds_once_when_it_is_due(client):
    item = create_item(kind="copy", platform="linkedin", item_type="post", text="Hello")
    later = create_item(kind="copy", platform="x", item_type="post", text="Later")
    client.put(f"/api/approvals/{item.id}/plan", json={"planned_at": iso(timedelta(hours=1))})
    client.put(f"/api/approvals/{later.id}/plan", json={"planned_at": iso(timedelta(days=3))})
    assert remind_due() == 0 and client.get("/api/approvals/due").json() == []

    move_back_in_time(item.id)
    assert remind_due() == 1
    assert remind_due() == 0  # only once
    due = client.get("/api/approvals/due").json()
    assert [d["id"] for d in due] == [item.id] and due[0]["due"] and due[0]["reminded_at"]
    assert "post_reminder" in [a["name"] for a in client.get("/api/activity?kind=action").json()]

    # Posting it ends the reminder.
    client.post(f"/api/approvals/{item.id}/posted")
    assert client.get("/api/approvals/due").json() == []


def test_no_reminders_while_paused(client):
    item = create_item(kind="copy", platform="linkedin", item_type="post", text="Hello")
    client.put(f"/api/approvals/{item.id}/plan", json={"planned_at": iso(timedelta(hours=1))})
    move_back_in_time(item.id)
    set_paused(True)
    assert remind_due() == 0
    set_paused(False)
    assert remind_due() == 1


def test_reminders_are_a_scheduler_job():
    from junior import scheduler

    assert ("post reminders", remind_due) in scheduler.JOBS
    assert scheduler.CHECK_EVERY_SECONDS <= 60
