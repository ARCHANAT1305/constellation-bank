/* Constellation UI: renders the agent event stream as a live orbit, a flight recorder, and a chat. */
const $ = (s, el = document) => el.querySelector(s);
const NS = 'http://www.w3.org/2000/svg';
const COLORS = { sup: '#f5b84b', customer: '#4fd1c5', risk: '#ff6b6b', credit: '#a78bfa' };
const sid = sessionStorage.sid || (sessionStorage.sid = Math.random().toString(36).slice(2));
const inr = n => '₹' + Math.round(n).toLocaleString('en-IN');
let AGENTS = {}, t0 = 0, busy = false;

const CHIPS = [
  ['customer', 'Balance & last 5 transactions', "What's my balance and last 5 transactions?"],
  ['customer', 'Spending summary', 'Summarize my spending this month'],
  ['risk', 'Check for fraud', "I see a charge I don't recognize. Check my recent transactions for fraud"],
  ['risk', 'Block my credit card', 'Block my credit card'],
  ['credit', '₹8L personal loan?', 'Can I get a ₹8 lakh personal loan for 60 months?'],
  ['credit', '₹30L counter-offer', 'Can I get a ₹30 lakh personal loan for 60 months?'],
  ['customer', 'Transfer ₹15,000 to Priya', 'Transfer ₹15,000 to Priya'],
  ['sup', 'Fraud + loan (multi-agent)', 'Something looks off on my card, and I also want to know if I qualify for a ₹5 lakh personal loan'],
  ['risk', 'Policy block: ₹5L transfer', 'Transfer ₹5 lakh to Rahul'],
];

/* ───────── orbit ───────── */
const C = { x: 300, y: 190 };
const POS = { customer: [140, 150], risk: [460, 150], credit: [300, 318] };
const svg = $('#orbit');
function el(tag, attrs = {}, parent = svg) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  parent.appendChild(e);
  return e;
}
function buildOrbit() {
  svg.innerHTML = '';
  const g0 = el('g', { class: 'spin' });
  el('circle', { cx: C.x, cy: C.y, r: 95, class: 'ring' }, g0);
  el('circle', { cx: C.x, cy: C.y, r: 150, class: 'ring' }, g0);
  el('ellipse', { cx: C.x, cy: C.y, rx: 288, ry: 186, class: 'guardring', id: 'guard' });
  el('text', { x: 300, y: 395, 'text-anchor': 'middle', 'font-size': 9, 'letter-spacing': '2' }).textContent = 'GUARDRAILS · PII MASKING · POLICY · HUMAN APPROVAL';
  // user
  const you = el('g', { class: 'you' });
  el('circle', { cx: 300, cy: 34, r: 14, fill: 'none', stroke: '#8a96a8', 'stroke-width': 1.5 }, you);
  el('text', { x: 300, y: 37, 'font-size': 9 }, you).textContent = 'YOU';
  el('line', { x1: 300, y1: 48, x2: 300, y2: 154, class: 'edge', id: 'e-you', style: '--c:' + COLORS.sup });
  // agents
  for (const [k, a] of Object.entries(AGENTS)) {
    const [ax, ay] = POS[k], col = a.color;
    el('line', { x1: C.x, y1: C.y, x2: ax, y2: ay, class: 'edge', id: 'e-' + k, style: '--c:' + col });
    const n = a.tools.length, base = Math.atan2(ay - C.y, ax - C.x);
    const span = Math.min(200, 36 * (n - 1)) * Math.PI / 180, step = n > 1 ? span / (n - 1) : 0;
    a.tools.forEach((tool, i) => {
      const ang = base + (i - (n - 1) / 2) * step;
      const sx = ax + Math.cos(ang) * 66, sy = ay + Math.sin(ang) * 66;
      const sens = tool === 'transfer_funds' || tool === 'block_card';
      const s = el('g', { class: 'sat' + (sens ? ' sens' : ''), id: `s-${tool}`, style: '--c:' + col });
      el('line', { x1: ax, y1: ay, x2: sx, y2: sy, stroke: col, 'stroke-opacity': .18 }, s);
      el('circle', { cx: sx, cy: sy, r: 5 }, s);
      el('title', {}, s).textContent = tool + (sens ? ' (needs approval)' : '');
    });
    const g = el('g', { class: 'node', id: 'n-' + k, style: '--c:' + col });
    el('circle', { cx: ax, cy: ay, r: 35, class: 'node-core' }, g);
    el('text', { x: ax, y: ay - 2, class: 'n' }, g).textContent = ({ customer: 'Customer', risk: 'Risk', credit: 'Credit' })[k];
    el('text', { x: ax, y: ay + 12, class: 'sub', id: 'tl-' + k }, g).textContent = ({ customer: 'banking', risk: 'fraud', credit: 'loans' })[k];
  }
  const sg = el('g', { class: 'node', id: 'n-sup', style: '--c:' + COLORS.sup });
  el('circle', { cx: C.x, cy: C.y, r: 44, class: 'node-core' }, sg);
  el('text', { x: C.x, y: C.y - 2, class: 'n' }, sg).textContent = 'Supervisor';
  el('text', { x: C.x, y: C.y + 12, class: 'sub' }, sg).textContent = 'orchestrator';
}
const on = (id, v) => { const n = document.getElementById(id); if (n) n.classList.toggle('on', v); };
const hint = t => $('#orbitHint').textContent = t;
function hitSat(tool, agent) {
  const s = document.getElementById('s-' + tool);
  if (s) { s.classList.add('hit'); setTimeout(() => s.classList.remove('hit'), 1100); }
  const l = document.getElementById('tl-' + agent); if (l) l.textContent = tool.length > 20 ? tool.slice(0, 19) + '…' : tool;
}
function hitGuard() { const g = $('#guard'); g.classList.add('hit'); setTimeout(() => g.classList.remove('hit'), 1200); }
function resetOrbit() {
  ['n-sup', 'n-customer', 'n-risk', 'n-credit', 'e-you', 'e-customer', 'e-risk', 'e-credit'].forEach(i => on(i, false));
  const sub = { customer: 'banking', risk: 'fraud', credit: 'loans' };
  for (const k in sub) { const l = $('#tl-' + k); if (l) l.textContent = sub[k]; }
  hint('idle · waiting for a request');
}

/* ───────── trace ───────── */
function trace(cls, color, tag, text, detail) {
  const box = $('#trace');
  const e0 = box.querySelector('.empty'); if (e0) e0.remove();
  const d = document.createElement('div');
  d.className = 'tr ' + cls; if (color) d.style.setProperty('--c', color);
  const ms = String(Math.max(0, Date.now() - t0)).padStart(4, ' ');
  d.innerHTML = `<span class="t">+${ms}ms</span><div><b>${esc(tag)}</b> ${text}` +
    (detail ? `<details><summary>${detail.label || 'details'}</summary><pre>${esc(JSON.stringify(detail.data, null, 2))}</pre></details>` : '') + '</div>';
  box.appendChild(d); box.scrollTop = box.scrollHeight;
}
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const short = o => esc(JSON.stringify(o)).slice(0, 110);

/* ───────── chat ───────── */
const chat = $('#chat');
function md(t) {
  const lines = esc(t).split('\n'); let out = '', ul = false;
  for (const ln of lines) {
    const li = ln.match(/^\s*[-•]\s+(.*)/);
    if (li) { if (!ul) { out += '<ul>'; ul = true; } out += `<li>${inline(li[1])}</li>`; continue; }
    if (ul) { out += '</ul>'; ul = false; }
    if (ln.trim()) out += `<p>${inline(ln)}</p>`;
  }
  return out + (ul ? '</ul>' : '');
}
const inline = s => s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/(^|\s)_(.+?)_(?=\s|$|[.,])/g, '$1<em>$2</em>');
function addUser(t) { const m = document.createElement('div'); m.className = 'msg user'; m.textContent = t; chat.appendChild(m); scroll(); }
function addBot() {
  const m = document.createElement('div'); m.className = 'msg bot';
  m.innerHTML = '<div class="by"></div><div class="body"><span class="typing">Supervisor is routing</span></div>';
  chat.appendChild(m); scroll(); return m;
}
const scroll = () => chat.scrollTop = chat.scrollHeight;
async function reveal(m, text) {
  const body = $('.body', m), words = text.split(/(\s+)/); let cur = '';
  for (let i = 0; i < words.length; i++) {
    cur += words[i];
    if (i % 3 === 0 || i === words.length - 1) { body.innerHTML = md(cur); scroll(); await new Promise(r => setTimeout(r, 14)); }
  }
}
function approvalCard(a) {
  const d = document.createElement('div'); d.className = 'msg bot';
  d.innerHTML = `<div class="approve"><div class="h">Human approval required</div><div class="s">${esc(a.summary)}</div>
    <div class="row"><button class="btn yes">Approve</button><button class="btn no">Reject</button></div></div>`;
  const card = $('.approve', d);
  const decide = async ok => {
    card.querySelectorAll('button').forEach(b => b.disabled = true);
    const r = await (await fetch(`/api/actions/${a.id}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approve: ok }) })).json();
    card.className = 'approve done ' + (r.ok && ok ? 'ok' : 'rej');
    card.innerHTML = `<div class="h">${r.ok ? (ok ? 'Approved · executed' : 'Rejected') : 'Failed'}</div><div class="s" style="margin:0">${esc(r.message || r.error || '')}</div>` +
      (r.result && r.result.reference ? `<div style="font:12px var(--mono);color:var(--muted);margin-top:6px">ref ${esc(r.result.reference)}</div>` : '');
    trace('appr', COLORS.sup, 'human_decision', `${ok ? 'approved' : 'rejected'} <span class="k">${esc(a.id)}</span>`, r.result ? { label: 'execution result', data: r.result } : null);
    loadSnap(true);
  };
  $('.yes', d).onclick = () => decide(true); $('.no', d).onclick = () => decide(false);
  chat.appendChild(d); scroll();
}

/* ───────── snapshot ───────── */
let lastSnap = '';
async function loadSnap(flash) {
  const s = await (await fetch('/api/snapshot')).json();
  const [sb, ca] = s.accounts, cc = s.cards.find(c => c.type === 'Credit'), dc = s.cards.find(c => c.type === 'Debit');
  const html = `
    <div class="s"><div class="l">Savings ••${sb.account_number.slice(-4)}</div><div class="v" data-k="sb">${inr(sb.balance)}</div><div class="sub">${esc(s.customer)}</div></div>
    <div class="s"><div class="l">Current ••${ca.account_number.slice(-4)}</div><div class="v" data-k="ca">${inr(ca.balance)}</div><div class="sub">Debit ••${dc.last4} <span class="pill ${dc.status}">${dc.status}</span></div></div>
    <div class="s"><div class="l">Credit card ••${cc.last4}<span class="pill ${cc.status}">${cc.status}</span></div><div class="v">${inr(cc.outstanding)}</div><div class="sub">of ${inr(cc.limit)} limit</div></div>`;
  if (html !== lastSnap) { $('#snap').innerHTML = html; if (flash) $('#snap').querySelectorAll('.v,.pill').forEach(n => n.classList.add('flash')); lastSnap = html; }
}

/* ───────── event stream ───────── */
async function ask(text) {
  if (busy || !text.trim()) return;
  busy = true; $('#send').disabled = true; $('#input').value = '';
  addUser(text); const bot = addBot(); t0 = Date.now(); resetOrbit();
  const pending = []; let agentsUsed = [];
  on('e-you', true); on('n-sup', true); hint('supervisor is classifying intent…');
  trace('sup', COLORS.sup, 'request', esc(text.length > 90 ? text.slice(0, 90) + '…' : text));
  try {
    const res = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: sid, message: text }) });
    const reader = res.body.getReader(), dec = new TextDecoder(); let buf = '';
    while (true) {
      const { value, done } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      let i; while ((i = buf.indexOf('\n')) >= 0) { const ln = buf.slice(0, i); buf = buf.slice(i + 1); if (ln.trim()) await onEvent(JSON.parse(ln), bot, pending, a => agentsUsed = a); }
    }
    for (const a of pending) approvalCard(a);
  } catch (e) {
    $('.body', bot).innerHTML = '<p>Something went wrong talking to the server. Is it running?</p>';
  }
  resetOrbit(); busy = false; $('#send').disabled = false; $('#input').focus();
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function onEvent(e, bot, pending, setAgents) {
  const col = e.agent ? AGENTS[e.agent]?.color : null, name = e.agent ? AGENTS[e.agent]?.label : '';
  switch (e.type) {
    case 'session': setBadge(e.mode, e); break;
    case 'guardrail': hitGuard(); trace('guard', '#7dd3fc', 'guardrail', esc(e.message)); break;
    case 'fallback': trace('policy', COLORS.risk, 'fallback', esc(e.message)); setBadge('offline'); break;
    case 'route':
      on('e-you', false); await sleep(250);
      trace('sup', COLORS.sup, 'route', `<span class="k">${esc(e.intent)}</span> → ${e.plan.length ? e.plan.map(p => AGENTS[p.agent].label).join(' → ') : '(direct reply)'}`,
        { label: 'supervisor decision · ' + e.mode, data: { reasoning: e.reasoning, plan: e.plan } });
      break;
    case 'agent_start':
      on('n-sup', false); on('e-' + e.agent, true); on('n-' + e.agent, true); hint(`${name} agent is working…`); const ty = $('.typing', bot); if (ty) ty.textContent = `${name} agent is working`;
      trace('', col, e.agent + '_agent', 'started'); await sleep(350); break;
    case 'tool_call':
      hitSat(e.tool, e.agent);
      trace('', col, 'tool_call', `<span class="k">${esc(e.tool)}</span>(${short(e.args)})${e.sensitive ? ' <b style="color:#f5b84b">sensitive</b>' : ''}`);
      await sleep(450); break;
    case 'tool_result': trace('', col, 'tool_result', `<span class="k">${esc(e.tool)} · ${e.ms}ms</span>`, { label: 'response', data: e.result }); break;
    case 'policy': hitGuard(); trace('policy', COLORS.risk, 'policy_block', esc(e.message)); break;
    case 'approval_required': pending.push(e.action); trace('appr', COLORS.sup, 'approval_required', `<span class="k">${esc(e.action.summary)}</span> (execution paused)`); break;
    case 'agent_done': on('e-' + e.agent, false); on('n-' + e.agent, false); trace('', col, e.agent + '_agent', 'finished'); break;
    case 'merge_start': on('n-sup', true); hint('supervisor is merging answers…'); trace('sup', COLORS.sup, 'merge', 'combining specialist answers'); await sleep(300); break;
    case 'final': {
      on('n-sup', false); setAgents(e.agents);
      const by = $('.by', bot);
      by.innerHTML = (e.agents.length ? e.agents : ['sup']).map(a => `<span class="tag" style="--c:${a === 'sup' ? COLORS.sup : AGENTS[a].color}">${a === 'sup' ? 'Supervisor' : AGENTS[a].label}</span>`).join('');
      trace('sup', COLORS.sup, 'final', 'answer delivered');
      await reveal(bot, e.text); break;
    }
  }
}
function setBadge(mode, e) {
  const b = $('#modeBadge'); b.className = 'badge ' + mode;
  b.textContent = mode === 'live' ? `LIVE · ${e?.supervisor_model || ''} + ${e?.agent_model || ''}` : 'OFFLINE SIMULATION · no API key';
}

/* ───────── boot ───────── */
async function boot() {
  const h = await (await fetch('/api/health')).json();
  AGENTS = h.agents; setBadge(h.mode, { supervisor_model: h.supervisor_model, agent_model: h.agent_model });
  buildOrbit(); loadSnap();
  $('#chips').innerHTML = CHIPS.map(([k, label], i) => `<button class="chip" data-i="${i}" style="--c:${COLORS[k]}"><i>●</i>${esc(label)}</button>`).join('');
  $('#chips').onclick = e => { const b = e.target.closest('.chip'); if (b) ask(CHIPS[b.dataset.i][2]); };
  chat.innerHTML = `<div class="welcome">Hi <b>Aarav</b>. This desk is run by a <b>Supervisor</b> that routes each request to specialist agents
    (<span style="color:${COLORS.customer}">Customer</span>, <span style="color:${COLORS.risk}">Risk &amp; Fraud</span>, <span style="color:${COLORS.credit}">Credit &amp; Loan</span>).
    Watch the constellation light up as they work. Money-moving actions always pause for <b>your approval</b>. Try a chip below.</div>`;
}
$('#form').onsubmit = e => { e.preventDefault(); ask($('#input').value); };
$('#clearTrace').onclick = () => $('#trace').innerHTML = '<div class="empty">Trace cleared.</div>';
$('#resetBtn').onclick = async () => { await fetch('/api/reset', { method: 'POST' }); lastSnap = ''; await loadSnap(true); boot(); $('#trace').innerHTML = '<div class="empty">Demo data reset.</div>'; };
boot();
