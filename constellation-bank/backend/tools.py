"""Simulated banking APIs, exposed to agents as tools (the 'Agent Tool / MCP layer')."""
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional

from . import data as D

S = D.STATE  # same dict object, mutated in place on reset


def _inr(x):
    return f"₹{x:,.0f}"


# ───────────────────────── Customer & Banking ─────────────────────────
def get_customer_profile():
    c = D.CUSTOMER
    return {"customer_id": c["id"], "name": c["name"], "segment": c["segment"], "since": c["customer_since"],
            "city": c["city"], "kyc_status": c["kyc_status"], "mobile": c["mobile"]}


def get_accounts():
    return {"accounts": [dict(a) for a in S["accounts"]], "cards": [dict(c) for c in S["cards"]]}


def get_beneficiaries():
    return {"beneficiaries": [dict(b) for b in S["beneficiaries"]]}


def _txn_view(t):
    return {k: t[k] for k in ("id", "ts", "merchant", "amount", "category", "channel", "city", "country", "source")}


def _recent(days):
    cutoff = datetime.now() - timedelta(days=days)
    rows = [t for t in S["transactions"] if datetime.fromisoformat(t["ts"]) >= cutoff]
    return sorted(rows, key=lambda t: t["ts"], reverse=True)


def get_transactions(days=30, category=None, limit=10):
    rows = _recent(days)
    if category:
        rows = [t for t in rows if t["category"].lower() == category.lower()]
    return {"count": len(rows), "transactions": [_txn_view(t) for t in rows[:limit]]}


def spending_summary(days=30):
    rows = _recent(days)
    by_cat, by_merchant = {}, {}
    for t in rows:
        by_cat[t["category"]] = by_cat.get(t["category"], 0) + t["amount"]
        by_merchant[t["merchant"]] = by_merchant.get(t["merchant"], 0) + t["amount"]
    total = sum(t["amount"] for t in rows)
    cats = sorted(by_cat.items(), key=lambda kv: -kv[1])
    return {
        "period_days": days, "total_spend": round(total, 2), "transaction_count": len(rows),
        "by_category": [{"category": k, "amount": v, "share_pct": round(100 * v / total, 1)} for k, v in cats],
        "top_merchants": [{"merchant": k, "amount": v} for k, v in sorted(by_merchant.items(), key=lambda kv: -kv[1])[:3]],
    }


def transfer_funds(beneficiary, amount, from_account="SB-4821"):  # executed only after approval
    acct = next(a for a in S["accounts"] if a["id"] == from_account)
    ben = next(b for b in S["beneficiaries"] if beneficiary.lower() in b["name"].lower())
    acct["balance"] = round(acct["balance"] - amount, 2)
    S["transactions"].append({
        "id": f"T-{uuid.uuid4().hex[:4].upper()}", "ts": datetime.now().isoformat(timespec="minutes"),
        "merchant": f"Transfer - {ben['name']}", "amount": amount, "category": "Transfer", "channel": "TRANSFER",
        "city": "Chennai", "country": "IN", "source": from_account, "status": "POSTED"})
    return {"status": "COMPLETED", "reference": f"IMPS{uuid.uuid4().hex[:8].upper()}", "to": ben["name"],
            "amount": amount, "new_balance": acct["balance"]}


def _validate_transfer(beneficiary, amount, from_account="SB-4821"):
    ben = next((b for b in S["beneficiaries"] if beneficiary.lower() in b["name"].lower()), None)
    if not ben:
        return False, f"'{beneficiary}' is not a saved beneficiary."
    if amount <= 0:
        return False, "Amount must be positive."
    if amount > 200000:
        return False, "Policy TXN-LIMIT-01: single transfers above ₹2,00,000 are not allowed via the assistant."
    acct = next((a for a in S["accounts"] if a["id"] == from_account), None)
    if not acct or acct["balance"] < amount:
        return False, "Insufficient balance in the source account."
    return True, ""


def _summary_transfer(beneficiary, amount, from_account="SB-4821"):
    ben = next(b for b in S["beneficiaries"] if beneficiary.lower() in b["name"].lower())
    return f"Transfer {_inr(amount)} from {from_account} to {ben['name']} ({ben['bank']})"


# ───────────────────────── Risk & Fraud ─────────────────────────
def _score(t):
    reasons, s = [], 0
    if t["country"] != D.CUSTOMER["home_country"]:
        s += 40
        reasons.append(f"International transaction ({t['country']}); customer's home country is IN")
        if t["channel"] == "ONLINE":
            s += 10
            reasons.append("Card-not-present transaction abroad")
    if 0 <= int(t["ts"][11:13]) < 5:
        s += 20
        reasons.append("Unusual hour (late night)")
    others = [x["amount"] for x in S["transactions"]
              if x["source"] == t["source"] and x["id"] != t["id"] and x["channel"] != "AUTO_DEBIT"]
    avg = sum(others) / len(others) if others else 0
    if avg and t["amount"] > 3 * avg:
        s += 20
        reasons.append(f"Amount is {t['amount'] / avg:.1f}x the card's average ticket ({_inr(avg)})")
    seen = sum(1 for x in S["transactions"] if x["merchant"] == t["merchant"])
    if seen == 1 and t["amount"] > 10000:
        s += 10
        reasons.append("First-ever high-value payment to this merchant")
    t_dt = datetime.fromisoformat(t["ts"])
    for x in S["transactions"]:
        if (x["id"] != t["id"] and x["merchant"] == t["merchant"] and x["amount"] == t["amount"]
                and abs((datetime.fromisoformat(x["ts"]) - t_dt).total_seconds()) <= 600):
            s += 35
            reasons.append(f"Possible duplicate charge (same merchant and amount as {x['id']} within 10 minutes)")
            break
    s = min(s, 100)
    level = "HIGH" if s >= 60 else "MEDIUM" if s >= 30 else "LOW"
    return s, level, reasons


def scan_transactions_for_anomalies(days=7):
    flagged = []
    rows = _recent(days)
    for t in rows:
        s, level, reasons = _score(t)
        if level != "LOW":
            flagged.append({**_txn_view(t), "risk_score": s, "risk_level": level, "reasons": reasons})
    flagged.sort(key=lambda x: -x["risk_score"])
    return {"scanned": len(rows), "flagged_count": len(flagged), "flagged": flagged}


def score_transaction(txn_id):
    t = next((x for x in S["transactions"] if x["id"].lower() == txn_id.lower()), None)
    if not t:
        return {"error": f"Transaction {txn_id} not found"}
    s, level, reasons = _score(t)
    return {**_txn_view(t), "risk_score": s, "risk_level": level, "reasons": reasons or ["No risk signals"]}


def get_card_status(card_id=None):
    cards = [c for c in S["cards"] if not card_id or c["id"] == card_id]
    return {"cards": [dict(c) for c in cards]}


def block_card(card_id, reason="Suspected fraud"):  # executed only after approval
    card = next(c for c in S["cards"] if c["id"] == card_id)
    card["status"] = "BLOCKED"
    return {"card_id": card_id, "status": "BLOCKED", "reason": reason,
            "reference": f"BLK{uuid.uuid4().hex[:6].upper()}",
            "next_step": "Replacement card will be dispatched in 5-7 working days. Disputes can be raised for flagged charges."}


def _validate_block(card_id, reason="Suspected fraud"):
    card = next((c for c in S["cards"] if c["id"] == card_id), None)
    if not card:
        return False, f"Card {card_id} not found."
    if card["status"] == "BLOCKED":
        return False, f"Card {card_id} is already blocked."
    return True, ""


def _summary_block(card_id, reason="Suspected fraud"):
    c = next(c for c in S["cards"] if c["id"] == card_id)
    return f"Block {c['type']} card ending {c['last4']} - reason: {reason}"


# ───────────────────────── Credit & Loan ─────────────────────────
def get_credit_profile():
    c = S["credit"]
    return {**c, "foir_current_pct": round(100 * c["existing_emi"] / c["monthly_income"], 1)}


def get_active_loans():
    return {"loans": [dict(l) for l in S["loans"]]}


def calculate_emi(principal, annual_rate, months):
    r = annual_rate / 1200
    emi = principal * r * (1 + r) ** months / ((1 + r) ** months - 1)
    return {"principal": principal, "annual_rate_pct": annual_rate, "months": months,
            "emi": round(emi), "total_interest": round(emi * months - principal), "total_payable": round(emi * months)}


_BASE_RATE = {"personal": 10.75, "auto": 8.9, "home": 8.4, "education": 9.0}
_MAX_TENURE = {"personal": 60, "auto": 84, "home": 360, "education": 120}
_PRODUCT_CAP = {"personal": 2500000, "auto": 3000000, "home": 50000000, "education": 4000000}


def check_loan_eligibility(loan_type, amount, tenure_months):
    loan_type = loan_type.lower()
    if loan_type not in _BASE_RATE:
        return {"error": f"Unknown loan type '{loan_type}'. Use personal, auto, home or education."}
    cp = S["credit"]
    score = cp["score"]
    if score < 650:
        return {"decision": "DECLINED", "reason": "Credit score below minimum of 650"}
    rate = _BASE_RATE[loan_type] + (0 if score >= 750 else 1.5 if score >= 700 else 3.0)
    tenure = min(tenure_months, _MAX_TENURE[loan_type])
    headroom = cp["monthly_income"] * 0.5 - cp["existing_emi"]  # FOIR cap of 50%
    emi = calculate_emi(amount, rate, tenure)["emi"]
    r = rate / 1200
    max_amount = int(headroom * ((1 + r) ** tenure - 1) / (r * (1 + r) ** tenure))
    max_amount = min(max_amount, _PRODUCT_CAP[loan_type])
    base = {"loan_type": loan_type, "requested_amount": amount, "tenure_months": tenure, "interest_rate_pct": rate,
            "estimated_emi": emi, "emi_headroom": round(headroom), "credit_score": score,
            "foir_after_loan_pct": round(100 * (cp["existing_emi"] + emi) / cp["monthly_income"], 1),
            "max_eligible_amount": max_amount}
    if amount > _PRODUCT_CAP[loan_type]:
        return {**base, "decision": "COUNTER_OFFER", "reason": f"Exceeds product cap of {_inr(_PRODUCT_CAP[loan_type])}"}
    if emi <= headroom:
        return {**base, "decision": "PRE_APPROVED", "reason": "EMI fits within the 50% FOIR limit. Subject to document verification."}
    return {**base, "decision": "COUNTER_OFFER",
            "reason": f"Requested EMI exceeds affordable headroom; you can borrow up to {_inr(max_amount)} over {tenure} months."}


# ───────────────────────── Registry ─────────────────────────
@dataclass
class Tool:
    name: str
    agent: str
    description: str
    schema: dict
    fn: Callable
    sensitive: bool = False
    validate: Optional[Callable] = None
    summarize: Optional[Callable] = None


def _obj(props=None, required=None):
    return {"type": "object", "properties": props or {}, "required": required or []}


_days = {"days": {"type": "integer", "description": "Look-back window in days"}}

TOOLS = {t.name: t for t in [
    Tool("get_customer_profile", "customer", "Get the customer's profile and KYC status.", _obj(), get_customer_profile),
    Tool("get_accounts", "customer", "List the customer's bank accounts (with balances) and cards.", _obj(), get_accounts),
    Tool("get_beneficiaries", "customer", "List saved payees the customer can transfer money to.", _obj(), get_beneficiaries),
    Tool("get_transactions", "customer", "Fetch recent transactions, newest first.",
         _obj({**_days, "category": {"type": "string"}, "limit": {"type": "integer"}}), get_transactions),
    Tool("spending_summary", "customer", "Summarise spend by category and merchant for a period.", _obj(_days), spending_summary),
    Tool("transfer_funds", "customer",
         "Request a fund transfer to a saved beneficiary. Never executes directly: creates a request the customer must approve.",
         _obj({"beneficiary": {"type": "string"}, "amount": {"type": "number"}, "from_account": {"type": "string"}},
              ["beneficiary", "amount"]),
         transfer_funds, True, _validate_transfer, _summary_transfer),
    Tool("scan_transactions_for_anomalies", "risk", "Run fraud rules over recent transactions and return flagged ones with reasons.",
         _obj(_days), scan_transactions_for_anomalies),
    Tool("score_transaction", "risk", "Risk-score one transaction by id (e.g. T-1001).",
         _obj({"txn_id": {"type": "string"}}, ["txn_id"]), score_transaction),
    Tool("get_card_status", "risk", "Get status (ACTIVE/BLOCKED) of cards.", _obj({"card_id": {"type": "string"}}), get_card_status),
    Tool("block_card", "risk",
         "Request blocking of a card. Never executes directly: creates a request the customer must approve.",
         _obj({"card_id": {"type": "string"}, "reason": {"type": "string"}}, ["card_id"]),
         block_card, True, _validate_block, _summary_block),
    Tool("get_credit_profile", "credit", "Get credit score, income and existing obligations.", _obj(), get_credit_profile),
    Tool("get_active_loans", "credit", "List the customer's active loans.", _obj(), get_active_loans),
    Tool("calculate_emi", "credit", "Calculate EMI for a principal, annual rate (%) and tenure in months.",
         _obj({"principal": {"type": "number"}, "annual_rate": {"type": "number"}, "months": {"type": "integer"}},
              ["principal", "annual_rate", "months"]), calculate_emi),
    Tool("check_loan_eligibility", "credit", "Check eligibility, rate and EMI for a loan (personal, auto, home, education).",
         _obj({"loan_type": {"type": "string"}, "amount": {"type": "number"}, "tenure_months": {"type": "integer"}},
              ["loan_type", "amount", "tenure_months"]), check_loan_eligibility),
]}


def tools_for(agent):
    return [t for t in TOOLS.values() if t.agent == agent]


# ───────────────────────── Guardrails ─────────────────────────
_MASK_KEYS = {"account_number", "mobile"}
_LONG_NUM = re.compile(r"(?:\d[ -]?){12,19}")


def redact_input(text):
    """PII detection on user input: card / account / Aadhaar-like numbers never reach the LLM."""
    found = []

    def sub(m):
        digits = re.sub(r"\D", "", m.group(0))
        found.append(digits[-4:])
        return "[REDACTED-NUMBER]"

    return _LONG_NUM.sub(sub, text), found


def mask_output(obj):
    """Mask account numbers / mobiles in tool results. Returns (masked, count)."""
    count = 0

    def walk(o):
        nonlocal count
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                if k in _MASK_KEYS and isinstance(v, str) and len(v) > 4:
                    out[k] = "X" * (len(v) - 4) + v[-4:]
                    count += 1
                else:
                    out[k] = walk(v)
            return out
        if isinstance(o, list):
            return [walk(i) for i in o]
        return o

    return walk(obj), count
