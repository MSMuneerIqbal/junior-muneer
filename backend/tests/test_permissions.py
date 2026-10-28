import pytest
from fastapi.testclient import TestClient

from junior.main import create_app
from junior.pause import set_paused
from junior.permissions import (
    CATALOG,
    AlreadyRun,
    RuleChangeError,
    claim_run,
    decide,
    finish_run,
    rule_for,
    set_mode,
    set_rule,
)


@pytest.fixture
def client():
    with TestClient(create_app(model_provider=lambda: (lambda n: None))) as c:
        yield c


# --- Defaults (PLAN.md section 8) ---------------------------------------------


@pytest.mark.parametrize(
    ("action_type", "rule"),
    [
        ("linkedin.post", "ask"),
        ("facebook.page.post", "ask"),
        ("gmail.send", "ask"),
        ("gmail.reply", "ask"),
        ("github.issue.create", "ask"),
        ("github.merge", "ask"),
        ("github.repo.delete", "deny"),
        ("github.force_push", "deny"),
        ("computer.read", "auto"),
        ("computer.write", "ask"),
        ("computer.delete", "ask"),
        ("computer.run", "ask"),
        ("system.payment", "deny"),
        ("system.password", "deny"),
        ("something.not_listed", "ask"),  # anything not listed: Ask
    ],
)
def test_defaults(client, action_type, rule):
    assert rule_for(action_type) == rule


def test_every_deny_default_is_locked():
    for t in CATALOG.values():
        if t.default == "deny":
            assert t.locked, t.key


# --- Changing rules ---------------------------------------------------------


def test_a_rule_can_be_switched_to_auto(client):
    set_rule("linkedin.post", "auto")
    d = decide("linkedin.post", from_outside=False)
    assert d.rule == "auto" and not d.can_always_allow
    set_rule("linkedin.post", "deny")
    assert decide("linkedin.post", from_outside=False).rule == "deny"


def test_whatsapp_mode_is_separate_and_persisted_on_cards(client):
    from junior.approvals import create_item
    from junior.db import ApprovalItem, session_scope
    from junior.permissions import ACTION_CHANNEL
    from junior.senders.guard import check
    from junior.settings_store import set_setting
    set_mode("rules")
    set_rule("computer.write", "auto")
    token = ACTION_CHANNEL.set("whatsapp")
    try:
        item = create_item(kind="api", platform="computer", item_type="file", text="example",
                           action_type="computer.write")
        assert item.status == "waiting" and item.meta["origin_channel"] == "whatsapp"
    finally:
        ACTION_CHANNEL.reset(token)
    assert decide("computer.write", from_outside=False).rule == "auto"
    set_setting("whatsapp_action_mode", "rules")
    token = ACTION_CHANNEL.set("whatsapp")
    try:
        auto = create_item(kind="api", platform="computer", item_type="file", text="example",
                           action_type="computer.write")
        assert auto.status == "approved"
    finally:
        ACTION_CHANNEL.reset(token)
    set_setting("whatsapp_action_mode", "ask_all")
    with session_scope() as session:
        assert any("needs your OK" in reason for reason in check(session.get(ApprovalItem, auto.id), "example"))


@pytest.mark.parametrize(
    "action_type",
    [t.key for t in CATALOG.values() if t.locked],
)
@pytest.mark.parametrize("rule", ["auto", "ask", "deny"])
def test_locked_types_cant_be_changed(client, action_type, rule):
    before = rule_for(action_type)
    with pytest.raises(RuleChangeError, match="locked"):
        set_rule(action_type, rule)
    assert rule_for(action_type) == before


def test_a_locked_rule_ignores_a_tampered_setting(client):
    from junior.settings_store import set_setting

    set_setting("permission_rules", {"github.repo.delete": "auto", "github.merge": "auto", "gmail.reply": "auto"})
    assert decide("github.repo.delete", from_outside=False).rule == "deny"
    assert decide("github.merge", from_outside=False).rule == "ask"
    assert decide("gmail.reply", from_outside=False).rule == "ask"


def test_bad_rules_and_types_are_refused(client):
    with pytest.raises(RuleChangeError):
        set_rule("linkedin.post", "always")
    with pytest.raises(RuleChangeError):
        set_rule("not a type", "ask")
    with pytest.raises(RuleChangeError):
        decide("rm -rf", from_outside=False)


def test_a_new_type_can_get_its_own_rule(client):
    set_rule("medium.post", "auto")
    assert decide("medium.post", from_outside=False).rule == "auto"


# --- Outside content --------------------------------------------------------


def test_outside_content_is_always_ask_even_when_auto(client):
    set_rule("linkedin.post", "auto")
    d = decide("linkedin.post", from_outside=True)
    assert d.rule == "ask"
    assert not d.can_always_allow
    assert "outside content" in d.reason


def test_outside_content_never_unlocks_a_deny(client):
    set_rule("linkedin.post", "deny")
    assert decide("linkedin.post", from_outside=True).rule == "deny"
    assert decide("system.payment", from_outside=True).rule == "deny"


def test_always_allow_offered_only_for_changeable_own_actions(client):
    assert decide("linkedin.post", from_outside=False).can_always_allow
    assert not decide("linkedin.post", from_outside=True).can_always_allow
    assert not decide("github.merge", from_outside=False).can_always_allow  # locked
    assert not decide("computer.run", from_outside=False).can_always_allow  # locked
    assert not decide("gmail.reply", from_outside=False).can_always_allow  # locked


# --- Global mode and pause ----------------------------------------------------


def test_ask_everything_turns_auto_into_ask(client):
    set_rule("linkedin.post", "auto")
    set_mode("ask_all")
    d = decide("linkedin.post", from_outside=False)
    assert d.rule == "ask" and "Manual mode" in d.reason
    assert decide("system.payment", from_outside=False).rule == "deny"  # Deny still wins
    set_mode("rules")
    assert decide("linkedin.post", from_outside=False).rule == "auto"


def test_bad_mode_is_refused(client):
    with pytest.raises(RuleChangeError):
        set_mode("yolo")


def test_pause_holds_everything(client):
    set_rule("linkedin.post", "auto")
    set_paused(True)
    assert decide("linkedin.post", from_outside=False).held
    assert decide("gmail.send", from_outside=False).held
    set_paused(False)
    assert not decide("linkedin.post", from_outside=False).held


# --- Run at most once ---------------------------------------------------------


def test_an_action_runs_at_most_once(client):
    run_id = claim_run("approval-1", "linkedin.post")
    with pytest.raises(AlreadyRun):
        claim_run("approval-1", "linkedin.post")
    finish_run(run_id, "failed", {"error": "timeout"})
    with pytest.raises(AlreadyRun):  # a failed run is retried on purpose, not automatically
        claim_run("approval-1", "linkedin.post")
    assert claim_run("approval-2", "linkedin.post") != run_id


# --- API and audit ------------------------------------------------------------


def test_api_lists_and_changes_rules(client):
    data = client.get("/api/permissions").json()
    assert data["mode"] == "rules" and data["paused"] is False
    types = {t["type"]: t for t in data["types"]}
    assert types["github.merge"]["locked"] and types["linkedin.post"]["rule"] == "ask"

    data = client.put("/api/permissions/rules/linkedin.post", json={"rule": "auto"}).json()
    assert {t["type"]: t for t in data["types"]}["linkedin.post"]["rule"] == "auto"

    r = client.put("/api/permissions/rules/github.merge", json={"rule": "auto"})
    assert r.status_code == 400 and "locked" in r.json()["detail"]
    assert client.put("/api/permissions/rules/linkedin.post", json={"rule": "maybe"}).status_code == 422

    assert client.put("/api/permissions/mode", json={"mode": "ask_all"}).json()["mode"] == "ask_all"

    names = [a["name"] for a in client.get("/api/activity?kind=setting").json()]
    assert "permission_rule" in names and "permission_mode" in names
    assert "permission_rules" not in client.get("/api/settings").json()


def test_plan_mode_shows_a_plan_and_queues_nothing(client):
    from junior.agent.context import TurnContext
    from junior.agent.tools import add_to_approvals_for
    from junior.settings_store import all_settings

    set_mode("plan")
    set_rule("linkedin.post", "auto")
    assert decide("linkedin.post", from_outside=False).rule == "ask"  # like Manual for actions
    context = TurnContext(conversation_id=None, settings=all_settings())
    assert add_to_approvals_for(context, "linkedin", "post", "Hello").startswith("NOT done: Plan mode is on")
    assert client.get("/api/approvals/count").json() == {"waiting": 0}

    from junior.agent.builder import render_instructions
    from junior.registry import load_registry

    text = render_instructions(load_registry().get("junior_muneer"), all_settings())
    assert "PLAN MODE IS ON" in text
    set_mode("rules")
    assert "PLAN MODE IS ON" not in render_instructions(load_registry().get("junior_muneer"), all_settings())
