# Demo video script (about 7 minutes)

**0:00 Intro (30s).** Show the screen. "This is Constellation, a multi-agent banking desk. A Supervisor routes requests to three agents:
Customer, Risk & Fraud, Credit & Loan. Badge shows live/offline mode."

**0:30 Architecture (60s).** Point at the orbit: supervisor centre, agents, satellite tools (dashed ones need approval), outer ring = guardrails.
Mention the mapping to the reference diagram (README table).

**1:30 Use case 1, balance (45s).** Click *Balance & last 5 transactions*. Show: supervisor lights up, route in recorder, Customer agent runs
`get_accounts` and `get_transactions`. Expand a response in the recorder: account number is masked (guardrail hit, blue ring flash).

**2:15 Use case 2, fraud (75s).** Click *Check for fraud*. Show the Lagos charge (100/100) and duplicate charge with reasons. Explain the explainable rules.

**3:30 Use case 3, human approval (75s).** Click *Block my credit card*. Show the amber approval card, then the card in the header is still ACTIVE.
Click Approve: header flips to BLOCKED. Say the LLM can never execute this itself.

**4:45 Use case 4, loans (60s).** Click *₹8L personal loan?* (pre-approved) then *₹30L counter-offer* (maximum eligible amount, FOIR rule).

**5:45 Multi-agent + policy (60s).** Click *Fraud + loan (multi-agent)*: two agents run in sequence, answers merged. Then *Policy block: ₹5L transfer*
to show the policy event in the recorder.

**6:45 Wrap (45s).** Open `orchestrator.py`: forced tool-call routing, per-agent tool sets, fallback to offline. Mention tests and next steps.
Tip: record once in live mode (with API key) to show real LLM routing reasoning (expand "supervisor decision").
