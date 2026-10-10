"""Supervisor + specialist agents.

Two execution modes share ONE event protocol so the UI is identical:
  live    - Claude tool-use loops (needs ANTHROPIC_API_KEY)
  offline - deterministic simulation (no key needed; also the automatic fallback on API errors)
"""
import json
import os
import re
import time
import uuid
from datetime import datetime

from . import data as D
from . import tools as T

SUPERVISOR_MODEL = os.getenv("SUPERVISOR_MODEL", "claude-haiku-5-5")
AGENT_MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-5-5")

try:
    import anthropic
    _client = anthropic.Anthropic() if os.getenv("ANTHROPIC_API_KEY") else None
except Exception:  # SDK missing
    _client = None

HISTORY = {}  # session_id -> [{"role","content"}]

AGENTS = {
    "customer": {"label": "Customer & Banking", "color": "#4fd1c5",
                 "role": "retail banking assistant: profile, accounts, balances, transactions, spending insights and fund transfers"},
    "risk": {"label": "Risk & Fraud", "color": "#ff6b6b",
             "role": "fraud analyst: anomaly detection, transaction risk scoring and card blocking"},
    "credit": {"label": "Credit & Loan", "color": "#a78bfa",
               "role": "credit officer: credit profile, loan eligibility, EMI calculation and counter-offers"},
}


def ev(type_, **kw):
    return {"type": type_, "ts": round(time.time(), 3), **kw}


def agent_system(agent):
    a = AGENTS[agent]
    return (f"You are the {a['label']} Agent, a {a['role']}, inside a SIMULATED retail bank (all data is synthetic). "
            f"Customer: {D.CUSTOMER['name']} ({D.CUSTOMER['id']}). Currency is INR; use Indian formatting (₹1,23,456 or lakh). "
            f"Today is {datetime.now():%A, %d %B %Y}. Always use tools to get facts; never invent numbers. "
            "Never print full account or card numbers. Sensitive actions (transfers, card blocks) are NEVER executed directly: "
            "calling the tool only creates a request that the customer must approve in the UI, so tell them it is awaiting their approval. "
            "If a tool reports a policy block, explain it plainly. Be concise (under ~120 words), use short bullets and **bold** for key figures.")


SUPERVISOR_SYSTEM = (
    "You are the Supervisor of a multi-agent banking desk. Classify the customer's request and route it.\n"
    "Agents: customer (accounts, balances, transactions, spending, transfers, profile); "
    "risk (fraud, suspicious or unrecognised charges, card blocking); credit (loans, EMI, eligibility, credit score).\n"
    "Pick the MINIMUM set of agents, in execution order. Give each a self-contained task string. "
    "If the message is a greeting or not about banking, return an empty plan and a short direct_reply. "
    "Use the conversation history to resolve references like 'that card' or 'it'."
)

ROUTE_TOOL = {
    "name": "route_request",
    "description": "Decide which specialist agents handle the request.",
    "input_schema": {"type": "object", "properties": {
        "intent": {"type": "string", "description": "Short label, e.g. fraud_check, loan_eligibility, balance_enquiry"},
        "reasoning": {"type": "string", "description": "One sentence on why these agents"},
        "plan": {"type": "array", "items": {"type": "object", "properties": {
            "agent": {"type": "string", "enum": ["customer", "risk", "credit"]},
            "task": {"type": "string"}}, "required": ["agent", "task"]}},
        "direct_reply": {"type": "string", "description": "Only when plan is empty"}},
        "required": ["intent", "reasoning", "plan"]},
}


def public_agents():
    return {k: {**v, "tools": [t.name for t in T.tools_for(k)]} for k, v in AGENTS.items()}


# ───────────────────────── tool execution (shared by both modes) ─────────────────────────
def tool_exec(agent, name, args):
    tool = T.TOOLS[name]
    yield ev("tool_call", agent=agent, tool=name, args=args, sensitive=tool.sensitive)
    t0 = time.time()
    try:
        if tool.sensitive:
            ok, why = tool.validate(**args)
            if not ok:
                yield ev("policy", agent=agent, tool=name, message=why)
                out = {"status": "BLOCKED_BY_POLICY", "reason": why}
            else:
                aid = f"ACT-{uuid.uuid4().hex[:6].upper()}"
                summary = tool.summarize(**args)
                D.PENDING[aid] = {"id": aid, "tool": name, "args": args, "agent": agent, "summary": summary, "status": "PENDING"}
                yield ev("approval_required", agent=agent, action={"id": aid, "tool": name, "summary": summary, "args": args})
                out = {"status": "PENDING_HUMAN_APPROVAL", "action_id": aid, "summary": summary}
        else:
            out = tool.fn(**args)
    except Exception as e:  # tool errors go back to the model, not the user
        out = {"error": f"{type(e).__name__}: {e}"}
    out, masked = T.mask_output(out)
    if masked:
        yield ev("guardrail", kind="pii_mask", message=f"Masked {masked} sensitive field(s) in {name} output")
    yield ev("tool_result", agent=agent, tool=name, result=out, ms=int((time.time() - t0) * 1000) + 12)
    return out


# ───────────────────────── live mode: Claude tool-use loop ─────────────────────────
def run_agent_live(agent, task):
    specs = [{"name": t.name, "description": t.description, "input_schema": t.schema} for t in T.tools_for(agent)]
    messages = [{"role": "user", "content": task}]
    for _ in range(6):
        resp = _client.messages.create(model=AGENT_MODEL, max_tokens=1200, system=agent_system(agent),
                                       tools=specs, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                out = yield from tool_exec(agent, b.name, dict(b.input))
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out, default=str)})
        messages.append({"role": "user", "content": results})
    return "I could not finish that request within the step limit."


def route_live(message, hist):
    ctx = "\n".join(f"{m['role']}: {m['content']}" for m in hist[-6:])
    prompt = f"Conversation so far:\n{ctx}\n\nNew customer message: {message}" if ctx else message
    resp = _client.messages.create(model=SUPERVISOR_MODEL, max_tokens=600, system=SUPERVISOR_SYSTEM,
                                   tools=[ROUTE_TOOL], tool_choice={"type": "tool", "name": "route_request"},
                                   messages=[{"role": "user", "content": prompt}])
    return next(b.input for b in resp.content if b.type == "tool_use")


def merge_live(message, answers):
    body = "\n\n".join(f"[{AGENTS[a]['label']}]\n{t}" for a, t in answers.items())
    resp = _client.messages.create(
        model=SUPERVISOR_MODEL, max_tokens=700,
        system="Merge specialist answers into ONE coherent reply to the customer. Keep every key figure and any pending-approval notice. "
               "No mention of internal agents. Under 170 words. Use short bullets and **bold**.",
        messages=[{"role": "user", "content": f"Customer asked: {message}\n\n{body}"}])
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ───────────────────────── offline mode: deterministic simulation ─────────────────────────
RISK_KW = ["fraud", "suspicious", "unauthori", "recognize", "recognise", "block", "stolen", "lost card", "scam",
           "unknown charge", "looks off", "off on my card", "hacked", "dispute"]
CREDIT_KW = ["loan", "emi", "credit score", "eligib", "borrow", "mortgage", "afford", "cibil", "qualify"]
CUSTOMER_KW = ["balance", "account", "spend", "spending", "statement", "transfer", "send ", "beneficiar", "profile", "transactions"]


def route_offline(message):
    t = message.lower()
    risk = any(k in t for k in RISK_KW)
    credit = any(k in t for k in CREDIT_KW)
    cust = any(k in t for k in CUSTOMER_KW if not (risk and k == "transactions"))
    plan = []
    for flag, agent in ((risk, "risk"), (credit, "credit"), (cust, "customer")):
        if flag:
            plan.append({"agent": agent, "task": message})
    if not plan:
        return {"intent": "smalltalk", "reasoning": "No banking intent detected.", "plan": [],
                "direct_reply": "Hi Aarav! I can check balances and spending, investigate suspicious charges, block a card, "
                                "move money to a saved payee, or check loan eligibility. What would you like to do?"}
    intent = "+".join({"risk": "fraud_check", "credit": "loan_eligibility", "customer": "account_enquiry"}[p["agent"]] for p in plan)
    names = " and ".join(AGENTS[p["agent"]]["label"] for p in plan)
    return {"intent": intent, "reasoning": f"Keyword intent match → {names}.", "plan": plan}


def parse_amount(text):
    t = text.lower().replace(",", "")
    for m in re.finditer(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|cr|k|thousand)?", t):
        n, unit = float(m.group(1)), m.group(2)
        mult = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7, "k": 1e3, "thousand": 1e3}.get(unit, 1)
        if unit or "₹" in m.group(0) or "rs" in m.group(0) or "inr" in m.group(0) or n >= 1000:
            return n * mult
    return None


def parse_months(text):
    t = text.lower()
    m = re.search(r"(\d+)\s*(?:months?|mos?\b)", t)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(?:years?|yrs?)", t)
    return int(m.group(1)) * 12 if m else None


def parse_loan_type(text):
    t = text.lower()
    for words, name in ((("home", "house", "mortgage"), "home"), (("car", "auto", "vehicle"), "auto"),
                        (("education", "study", "student"), "education")):
        if any(re.search(rf"\b{w}\b", t) for w in words):
            return name
    return "personal"


def off_customer(task):
    t = task.lower()
    if "transfer" in t or "send " in t:
        bens = (yield from tool_exec("customer", "get_beneficiaries", {}))["beneficiaries"]
        ben = next((b for b in bens if any(p in t for p in b["name"].lower().replace("(", "").replace(")", "").split() if len(p) > 3)), None)
        amt = parse_amount(task)
        if not ben or not amt:
            names = ", ".join(b["name"] for b in bens)
            return f"Tell me **who** and **how much**, e.g. “Transfer ₹15,000 to Priya”. Saved payees: {names}."
        out = yield from tool_exec("customer", "transfer_funds", {"beneficiary": ben["name"], "amount": amt})
        if out.get("status") == "PENDING_HUMAN_APPROVAL":
            return f"I've prepared a transfer of **₹{amt:,.0f}** to **{ben['name']}**. It needs your approval before it goes out; use the card below."
        return f"I couldn't set that up: {out.get('reason', out)}"
    if "spend" in t or "summar" in t:
        out = yield from tool_exec("customer", "spending_summary", {"days": 30})
        lines = [f"- **{c['category']}**: ₹{c['amount']:,.0f} ({c['share_pct']}%)" for c in out["by_category"][:5]]
        return (f"Over the last 30 days you spent **₹{out['total_spend']:,.0f}** across {out['transaction_count']} transactions. Top categories:\n"
                + "\n".join(lines))
    acc = yield from tool_exec("customer", "get_accounts", {})
    tx = yield from tool_exec("customer", "get_transactions", {"days": 30, "limit": 5})
    lines = [f"- {a['type']} (…{a['account_number'][-4:]}): **₹{a['balance']:,.2f}**" for a in acc["accounts"]]
    tl = [f"- {x['ts'][5:10]} · {x['merchant']}: ₹{x['amount']:,.0f}" for x in tx["transactions"]]
    return "Your balances:\n" + "\n".join(lines) + "\n\nLast 5 transactions:\n" + "\n".join(tl)


def off_risk(task):
    t = task.lower()
    m = re.search(r"t-\d{4}", t)
    if m:
        s = yield from tool_exec("risk", "score_transaction", {"txn_id": m.group(0).upper()})
        if "error" in s:
            return s["error"]
        return (f"**{s['id']}** at {s['merchant']} (₹{s['amount']:,.0f}) scores **{s['risk_score']}/100 ({s['risk_level']})**:\n"
                + "\n".join(f"- {r}" for r in s["reasons"]))
    if "block" in t or "stolen" in t or "lost card" in t:
        card = "DC-3377" if "debit" in t else "CC-1190"
        yield from tool_exec("risk", "get_card_status", {"card_id": card})
        out = yield from tool_exec("risk", "block_card", {"card_id": card, "reason": "Customer requested block"})
        if out.get("status") == "PENDING_HUMAN_APPROVAL":
            return f"I've prepared a request to block your card **{card}**. Please confirm it with the approval card below."
        return out.get("reason", "That card can't be blocked right now.")
    res = yield from tool_exec("risk", "scan_transactions_for_anomalies", {"days": 7})
    if not res["flagged"]:
        return f"I scanned {res['scanned']} recent transactions and found nothing unusual."
    lines = []
    for f in res["flagged"]:
        lines.append(f"- **{f['merchant']}** ₹{f['amount']:,.0f} ({f['id']}): **{f['risk_level']} risk ({f['risk_score']}/100)**; {f['reasons'][0]}")
    top = res["flagged"][0]
    tail = ("\n\nThe top item looks like card-not-present fraud. I recommend blocking card **CC-1190**; just say “block my credit card”."
            if top["risk_level"] == "HIGH" else "")
    return f"I scanned {res['scanned']} transactions from the last 7 days and flagged {res['flagged_count']}:\n" + "\n".join(lines) + tail


def off_credit(task):
    amt = parse_amount(task)
    if not amt:
        p = yield from tool_exec("credit", "get_credit_profile", {})
        l = yield from tool_exec("credit", "get_active_loans", {})
        loan = l["loans"][0] if l["loans"] else None
        extra = (f"\n- Active {loan['type']} loan: ₹{loan['outstanding']:,.0f} outstanding, EMI ₹{loan['emi']:,.0f}" if loan else "")
        return (f"- Credit score: **{p['score']}**\n- Monthly income: ₹{p['monthly_income']:,.0f}\n"
                f"- Current obligations (FOIR): **{p['foir_current_pct']}%**" + extra +
                "\n\nTell me an amount, e.g. “Can I get a ₹8 lakh personal loan for 60 months?”")
    ltype = parse_loan_type(task)
    months = parse_months(task) or {"personal": 60, "auto": 60, "home": 240, "education": 84}[ltype]
    yield from tool_exec("credit", "get_credit_profile", {})
    r = yield from tool_exec("credit", "check_loan_eligibility", {"loan_type": ltype, "amount": amt, "tenure_months": months})
    if "error" in r:
        return r["error"]
    head = {"PRE_APPROVED": "✅ **Pre-approved**", "COUNTER_OFFER": "↔️ **Counter-offer**", "DECLINED": "❌ **Declined**"}[r["decision"]]
    out = (f"{head} for a ₹{r['requested_amount']:,.0f} {r['loan_type']} loan over {r['tenure_months']} months.\n"
           f"- Rate: **{r['interest_rate_pct']}%** (credit score {r['credit_score']})\n"
           f"- Estimated EMI: **₹{r['estimated_emi']:,.0f}** (FOIR after loan {r['foir_after_loan_pct']}%)\n")
    if r["decision"] == "COUNTER_OFFER":
        out += f"- You can comfortably borrow up to **₹{r['max_eligible_amount']:,.0f}**.\n"
    return out + f"\n_{r['reason']}_"


OFFLINE_AGENTS = {"customer": off_customer, "risk": off_risk, "credit": off_credit}


# ───────────────────────── main entry ─────────────────────────
def handle(session_id, message):
    live = _client is not None
    yield ev("session", mode="live" if live else "offline",
             supervisor_model=SUPERVISOR_MODEL if live else "rule-router",
             agent_model=AGENT_MODEL if live else "scripted-agents")
    clean, found = T.redact_input(message)
    if found:
        yield ev("guardrail", kind="pii_detect", message=f"Redacted {len(found)} account/card-like number(s) from your message before routing")
    hist = HISTORY.setdefault(session_id, [])

    yield ev("supervisor_start")
    route = None
    if live:
        try:
            route = route_live(clean, hist)
        except Exception as e:
            live = False
            yield ev("fallback", message=f"LLM unavailable ({type(e).__name__}); switching to offline simulation")
    if route is None:
        route = route_offline(clean)
    plan = route.get("plan") or []
    yield ev("route", intent=route.get("intent", ""), reasoning=route.get("reasoning", ""), plan=plan, mode="live" if live else "offline")

    if not plan:
        text = route.get("direct_reply") or "I can help with banking questions: accounts, fraud checks, cards and loans."
        yield ev("final", text=text, agents=[])
        hist += [{"role": "user", "content": clean}, {"role": "assistant", "content": text}]
        return

    answers = {}
    for step in plan:
        agent, task = step["agent"], step["task"]
        yield ev("agent_start", agent=agent, task=task)
        text = None
        if live:
            try:
                text = yield from run_agent_live(agent, task)
            except Exception as e:
                live = False
                yield ev("fallback", message=f"LLM error in {agent} agent ({type(e).__name__}); using offline simulation")
        if text is None:
            text = yield from OFFLINE_AGENTS[agent](task)
        answers[agent] = text
        yield ev("agent_done", agent=agent, text=text)

    if len(answers) == 1:
        final = next(iter(answers.values()))
    else:
        yield ev("merge_start")
        final = None
        if live:
            try:
                final = merge_live(clean, answers)
            except Exception:
                final = None
        if final is None:
            final = "\n\n".join(f"**{AGENTS[a]['label']}**\n{t}" for a, t in answers.items())
    yield ev("final", text=final, agents=list(answers))
    hist += [{"role": "user", "content": clean}, {"role": "assistant", "content": final}]
    del hist[:-12]


def decide(action_id, approve):
    act = D.PENDING.get(action_id)
    if not act or act["status"] != "PENDING":
        return {"ok": False, "error": "Action not found or already decided"}
    if not approve:
        act["status"] = "REJECTED"
        return {"ok": True, "status": "REJECTED", "message": f"Rejected: {act['summary']}. Nothing was changed."}
    tool = T.TOOLS[act["tool"]]
    ok, why = tool.validate(**act["args"])  # re-validate at execution time
    if not ok:
        act["status"] = "FAILED"
        return {"ok": False, "status": "FAILED", "error": why}
    result = tool.fn(**act["args"])
    act["status"] = "APPROVED"
    return {"ok": True, "status": "APPROVED", "result": result, "message": f"Done: {act['summary']}."}
