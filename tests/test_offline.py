"""Runs fully offline (no API key needed): routing, tools, guardrails, human approval."""
import json
import os

os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

client = TestClient(app)


def chat(msg, sid="t"):
    r = client.post("/api/chat", json={"session_id": sid, "message": msg})
    return [json.loads(l) for l in r.text.splitlines() if l]


def route_agents(events):
    return [s["agent"] for s in next(e for e in events if e["type"] == "route")["plan"]]


def setup_function(_):
    client.post("/api/reset")


def test_health_lists_three_agents():
    h = client.get("/api/health").json()
    assert set(h["agents"]) == {"customer", "risk", "credit"}


def test_balance_routes_to_customer():
    ev = chat("What's my balance and last 5 transactions?")
    assert route_agents(ev) == ["customer"]
    assert any(e["type"] == "tool_call" and e["tool"] == "get_accounts" for e in ev)
    final = next(e for e in ev if e["type"] == "final")["text"]
    assert "184,250.75" in final
    # account numbers must be masked by the guardrail
    assert "50100234884821" not in json.dumps(ev)
    assert any(e["type"] == "guardrail" and e["kind"] == "pii_mask" for e in ev)


def test_fraud_scan_flags_lagos_and_duplicate():
    ev = chat("I see a charge I don't recognize, check my recent transactions for fraud")
    assert route_agents(ev) == ["risk"]
    res = next(e for e in ev if e["type"] == "tool_result" and e["tool"] == "scan_transactions_for_anomalies")["result"]
    ids = {f["id"]: f for f in res["flagged"]}
    assert ids["T-1001"]["risk_level"] == "HIGH"
    assert "T-1003" in ids and "T-1004" in ids


def test_block_card_requires_human_approval():
    ev = chat("Block my credit card")
    appr = next(e for e in ev if e["type"] == "approval_required")["action"]
    cards = client.get("/api/snapshot").json()["cards"]
    assert next(c for c in cards if c["id"] == "CC-1190")["status"] == "ACTIVE"  # not executed yet
    r = client.post(f"/api/actions/{appr['id']}/decision", json={"approve": True}).json()
    assert r["ok"] and r["status"] == "APPROVED"
    cards = client.get("/api/snapshot").json()["cards"]
    assert next(c for c in cards if c["id"] == "CC-1190")["status"] == "BLOCKED"
    # cannot be replayed
    assert not client.post(f"/api/actions/{appr['id']}/decision", json={"approve": True}).json()["ok"]


def test_transfer_reject_changes_nothing_and_approve_moves_money():
    ev = chat("Transfer ₹15,000 to Priya")
    appr = next(e for e in ev if e["type"] == "approval_required")["action"]
    before = client.get("/api/snapshot").json()["accounts"][0]["balance"]
    client.post(f"/api/actions/{appr['id']}/decision", json={"approve": False})
    assert client.get("/api/snapshot").json()["accounts"][0]["balance"] == before
    appr2 = next(e for e in chat("Transfer ₹15,000 to Priya") if e["type"] == "approval_required")["action"]
    client.post(f"/api/actions/{appr2['id']}/decision", json={"approve": True})
    assert client.get("/api/snapshot").json()["accounts"][0]["balance"] == before - 15000


def test_transfer_over_policy_limit_is_blocked():
    ev = chat("Transfer ₹5 lakh to Rahul")
    assert any(e["type"] == "policy" for e in ev)
    assert not any(e["type"] == "approval_required" for e in ev)


def test_loan_preapproved_and_counter_offer():
    ev = chat("Can I get a ₹8 lakh personal loan for 60 months?")
    assert route_agents(ev) == ["credit"]
    r = next(e for e in ev if e["type"] == "tool_result" and e["tool"] == "check_loan_eligibility")["result"]
    assert r["decision"] == "PRE_APPROVED"
    ev = chat("Can I get a ₹30 lakh personal loan for 60 months?")
    r = next(e for e in ev if e["type"] == "tool_result" and e["tool"] == "check_loan_eligibility")["result"]
    assert r["decision"] == "COUNTER_OFFER" and r["max_eligible_amount"] < 3000000


def test_multi_agent_request():
    ev = chat("Something looks off on my card, and also can I get a ₹5 lakh loan?")
    assert route_agents(ev) == ["risk", "credit"]
    assert any(e["type"] == "merge_start" for e in ev)


def test_pii_in_input_is_redacted():
    ev = chat("My card 4111 1111 1111 1111 looks off, check fraud")
    assert any(e["type"] == "guardrail" and e["kind"] == "pii_detect" for e in ev)


def test_smalltalk_gets_direct_reply():
    ev = chat("hello there")
    assert route_agents(ev) == []
    assert next(e for e in ev if e["type"] == "final")["text"]


def test_loan_type_not_confused_by_word_card():
    ev = chat("Something looks off on my card, and can I get a ₹5 lakh personal loan?")
    r = next(e for e in ev if e["type"] == "tool_result" and e["tool"] == "check_loan_eligibility")["result"]
    assert r["loan_type"] == "personal"
