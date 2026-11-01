(() => {
  const host = document.getElementById('extras');
  if (!host) return;
  const mk = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c; if (x !== undefined) e.textContent = x; return e; };
  const get = async (p, o) => { const r = await fetch(p, o); if (!r.ok) throw new Error((await r.text()).slice(0, 200)); return r.json(); };
  const card = (title, sub) => { const c = mk('div', 'card'); c.append(mk('h2', null, title)); if (sub) c.append(mk('div', 'muted', sub)); host.append(c); return c; };
  const usd = c => '$' + (c / 100).toFixed(2);

  // 1. Tamper-evident audit chain
  const a = card('Audit chain', 'Every decision and status change is hash-chained. Editing history is detectable.');
  const status = mk('div'), meta = mk('div', 'muted'), probs = mk('ul'), row = mk('div', 'row');
  const bVerify = mk('button', 'ghost', 'Verify now'), bTamper = mk('button', 'ghost', 'Simulate tampering');
  row.append(bVerify, bTamper); a.append(status, meta, probs, row);
  async function verify() {
    try {
      const v = await get('/api/audit/verify');
      status.replaceChildren(mk('span', 'badge ' + (v.ok ? 'CAPTURED' : 'BLOCKED'), v.ok ? 'CHAIN VERIFIED' : 'TAMPERING DETECTED'));
      meta.textContent = v.events + ' audit events, head ' + v.head.slice(0, 12);
      probs.replaceChildren(...v.problems.map(p => mk('li', null, p)));
    } catch (e) { meta.textContent = e.message; }
  }
  bVerify.onclick = verify;
  bTamper.onclick = async () => {
    try { await get('/api/audit/tamper', { method: 'POST' }); } catch (e) { meta.textContent = e.message; return; }
    if (typeof refresh === 'function') await refresh();
    verify();
  };

  // 2. Live merchant intelligence
  const m = card('Store intelligence', 'Live domain-age and DNS check for any store the agent might find.');
  const inp = mk('input'); inp.type = 'text'; inp.placeholder = 'example-store.com';
  const bCheck = mk('button', null, 'Check store'), out = mk('div'), mrow = mk('div', 'row');
  mrow.append(inp, bCheck); m.append(mrow, out);
  bCheck.onclick = async () => {
    out.replaceChildren(mk('p', 'muted', 'Looking up...'));
    try {
      const r = await get('/api/intel?domain=' + encodeURIComponent(inp.value));
      if (r.error) { out.replaceChildren(mk('p', 'muted', r.error)); return; }
      const ul = mk('ul'); r.reasons.forEach(x => ul.append(mk('li', null, x)));
      out.replaceChildren(mk('b', null, r.domain + ' '), mk('span', 'badge ' + r.verdict, r.verdict), ul);
    } catch (e) { out.replaceChildren(mk('div', 'banner BLOCKED', e.message)); }
  };

  // 3. Extended attack suite
  const x = card('Extended attack suite', 'Eight more attacks, including obfuscation tricks. The library grows with every red-team finding.');
  const bExt = mk('button', null, 'Run extended suite'), tiles = mk('p', 'muted'), list = mk('div');
  x.append(bExt, tiles, list);
  bExt.onclick = async () => {
    try {
      const r = await get('/api/attacks?suite=extended');
      tiles.textContent = r.attempts + ' attacks: ' + r.blocked + ' blocked, ' + r.escalated + ' escalated, ' + r.leaked + ' leaked. ' + usd(r.protected_cents) + ' attempted loss prevented.';
      list.replaceChildren(...r.rows.map(a => {
        const d = mk('div', 'step ' + (a.verdict === 'BLOCK' ? 'BLOCK' : 'REVIEW'));
        d.append(mk('b', null, a.attack + ' '), mk('span', 'badge ' + a.verdict, a.verdict), mk('div', 'muted', a.technique));
        return d;
      }));
    } catch (e) { tiles.textContent = e.message; }
  };

  if (typeof refresh === 'function') {
    const orig = refresh;
    window.refresh = async () => { await orig(); verify(); };
  }
  verify();
})();
