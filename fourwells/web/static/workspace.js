/* Scientific workspace. Uses saved evidence, never fills absent objectives. */
(function () {
  'use strict';
  const view = () => document.getElementById('view');
  const esc = x => String(x == null ? '' : x).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const api = async path => { const r = await fetch('/api/experiments' + path); if (!r.ok) throw Error(await r.text()); return r.json(); };
  const url = id => '/experiments/' + encodeURIComponent(id);
  const metric = o => o && o.status === 'available' ? `${Number(o.value).toPrecision(4)} ${esc(o.unit)} · ${esc(o.kind)} · ${esc(o.method)}` : 'unknown';
  let openCandidate = null, comparePicks = [], pageKey = '', cache = '';
  const status = j => `<span class="badge ${esc(j.status)}">${esc(j.status)}</span>`;
  function error(e) { view().innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
  function table(jobs) {
    return `<div class="panel"><table><thead><tr><th>Iteration</th><th>Question</th><th>Mode / status</th><th>Candidates</th><th>Eligible / shortlisted</th><th>Created</th></tr></thead><tbody>${jobs.map(j => `<tr><td><a href="${url(j.id)}"><code>${esc(j.id)}</code></a></td><td>${esc(j.spec.question)}</td><td>${esc(j.spec.mode)} ${status(j)}</td><td>${j.result ? j.result.counts.generated : '—'}</td><td>${j.result ? j.result.counts.eligible + ' / ' + j.result.counts.shortlisted : '—'}</td><td>${esc(new Date(j.created).toLocaleString())}</td></tr>`).join('')}</tbody></table></div>`;
  }
  async function list() {
    const d = await api('');
    view().innerHTML = `<h1>AntibodyLab AI</h1><p class="muted">HER2 · trastuzumab reference · immutable scientific iterations</p>
      <div class="note">Official validation controls eligibility. Unknown thermostability stays unknown. Structural confidence is not measured affinity.</div>
      ${d.resources ? `<details><summary>Local model resources</summary><ul>${Object.entries(d.resources.tools).map(([name, found]) => `<li>${esc(name)}: ${found ? 'executable found' : 'not found'}</li>`).join('')}<li>Organizer README in default data locations: ${d.resources.organizer_readme ? 'found' : 'not found'}</li><li>VM instructions / tutorial in ~/rfd4: ${d.resources.vm_instructions ? 'found' : 'not found'} / ${d.resources.model_tutorial ? 'found' : 'not found'}</li></ul><p>${esc(d.resources.note)}</p></details>` : ''}
      <details id="new-experiment"><summary class="btn">New offline experiment</summary><form id="experiment-form">
      <p><label>Question this iteration answers <input id="question" required maxlength="2000" placeholder="Does a different seed add sequence diversity?"></label></p>
      <p><label>Seed <input id="seed" type="number" min="0" max="2147483647" value="0" required></label>
      <label>Candidates <input id="count" type="number" min="1" max="1000" value="24" required></label></p>
      <p><label>Parent iteration (optional) <select id="parent"><option value="">None</option>${d.iterations.map(j => `<option value="${esc(j.id)}">${esc(j.id)}</option>`).join('')}</select></label></p>
      <p class="muted">Demo sequences are for exercising the workflow. They cannot be exported as eligible designs.</p>
      <button class="btn" type="submit">Start offline demo</button><p id="start-error" role="alert"></p></form></details>
      <p class="muted">Import saved candidates or run installed models from the CLI; jobs continue after closing the browser.</p>
      <h2>Iterations</h2>${d.iterations.length ? table(d.iterations) : '<p>No scientific iterations yet. Start an offline experiment above.</p>'}`;
    document.getElementById('experiment-form').onsubmit = async e => {
      e.preventDefault(); const button = e.target.querySelector('button'); button.disabled = true;
      try {
        const payload = {mode:'demo', question:document.getElementById('question').value,
          seed:Number(document.getElementById('seed').value), candidates:Number(document.getElementById('count').value)};
        if (document.getElementById('parent').value) payload.parent = document.getElementById('parent').value;
        const r = await fetch('/api/experiments', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
        const j = await r.json(); if (!r.ok) throw Error(j.error); location.href = url(j.id);
      } catch (e) { document.getElementById('start-error').textContent = e.message; button.disabled = false; }
    };
  }
  function objectiveTable(c) {
    return `<table><thead><tr><th>Objective</th><th>Evidence</th><th>Baseline</th><th>Source / limitations</th></tr></thead><tbody>${['binding','epitope','stability'].map(a => {
      const o = c.objectives[a];
      return `<tr><td>${a === 'stability' ? 'Thermostability' : a}</td><td>${metric(o)}</td><td>${esc(o.reference_value == null ? 'unknown' : o.reference_value)}</td><td>${esc(o.source || o.reason)}<br>${esc(o.limitations || '')}</td></tr>`;
    }).join('')}</tbody></table>`;
  }
  function objectivePlots(candidates) {
    const groups = new Map();
    candidates.forEach(c => ['binding','epitope','stability'].forEach(axis => {
      const o = c.objectives[axis]; if (!o || o.status !== 'available') return;
      const key = JSON.stringify([axis,o.method,o.version,o.unit,o.direction,o.kind]);
      if (!groups.has(key)) groups.set(key, {axis,o,points:[]});
      groups.get(key).points.push({c,o});
    }));
    if (!groups.size) return '<p class="muted">No supported objective values to plot. Missing evidence is not plotted as zero.</p>';
    return '<p class="muted">Raw evidence on separate scales for each method, version, unit and evidence kind. Hover or focus a point for its candidate. Green points are shortlisted.</p>' + [...groups.values()].map(g => {
      const values = g.points.map(p => p.o.value);
      const refs = g.points.map(p => p.o.reference_value).filter(v => v != null);
      const lo = Math.min(...values,...refs), hi = Math.max(...values,...refs), span = hi-lo || 1;
      const x = v => 36 + (hi === lo ? 264 : (v-lo)/span*528);
      const height = 105;
      return `<figure class="objective-plot"><figcaption><strong>${esc(g.axis === 'stability' ? 'Thermostability' : g.axis)}</strong> · ${esc(g.o.method)} v${esc(g.o.version)} · ${esc(g.o.kind)} · ${esc(g.o.unit)} · ${g.o.direction === 'min' ? 'lower' : 'higher'} is better</figcaption>
        <svg viewBox="0 0 600 ${height}" role="img" aria-label="${esc(g.axis)} objective values"><line x1="36" y1="66" x2="564" y2="66" stroke="currentColor" opacity=".4"/>
        ${[...new Set(refs)].map(v => `<line x1="${x(v)}" y1="14" x2="${x(v)}" y2="70" stroke="currentColor" opacity=".4" stroke-dasharray="4 3"><title>Supplied baseline: ${esc(v)} ${esc(g.o.unit)}</title></line>`).join('')}
        ${g.points.map((p,i) => `<circle tabindex="0" cx="${x(p.o.value)}" cy="${24 + i%4*10}" r="5" fill="${p.c.selected ? '#39ba86' : '#5c91ee'}"><title>${esc(p.c.iteration_label ? p.c.iteration_label + ' / ' : '')}${esc(p.c.design_id)}: ${esc(p.o.value)} ${esc(p.o.unit)} · ${esc(p.c.validation.status)}</title></circle>`).join('')}
        <text x="36" y="88" fill="currentColor" font-size="12">${Number(lo).toPrecision(4)}</text><text x="564" y="88" text-anchor="end" fill="currentColor" font-size="12">${Number(hi).toPrecision(4)}</text></svg></figure>`;
    }).join('');
  }
  function diversityTable(pairs) {
    if (!pairs || !pairs.length) return '<p class="muted">At least two shortlisted candidates are needed for pairwise diversity.</p>';
    return `<p class="muted">Global alignment matches divided by the longer sequence length. Higher identity means less diversity; full constructs are compared when either CDRH3 is unavailable.</p><table><thead><tr><th>Candidate A</th><th>Candidate B</th><th>Scope</th><th>Identity</th></tr></thead><tbody>${pairs.map(p => `<tr><td>${esc(p.a)}</td><td>${esc(p.b)}</td><td>${esc(p.scope || 'CDRH3')}</td><td>${(100*(p.identity == null ? p.cdrh3_identity : p.identity)).toFixed(1)}%</td></tr>`).join('')}</tbody></table>`;
  }
  function candidate(c, job) {
    return `<section class="candidate"><h3>${esc(c.design_id)} · ${esc(c.decision)}</h3>
      <p>${esc(c.format || 'format unknown')} · track: ${esc(c.track || 'not assigned by abguard')} · generator ${esc(c.generator || 'unknown')} ${c.stub ? '<strong class="stub">DEMO</strong>' : ''}</p>
      <pre class="sequence">${esc(c.sequence)}</pre><p>CDRH3: <code>${esc(c.cdrh3 || 'unknown')}</code></p>
      ${objectiveTable(c)}
      <details><summary>Official validation and local screening</summary><pre>${esc(JSON.stringify(c.validation,null,2))}</pre></details>
      <details><summary>Generation parameters and provenance</summary><pre>${esc(JSON.stringify(c.generation,null,2))}</pre></details>
      <details><summary>Prediction metrics and model disagreement</summary><pre>${esc(JSON.stringify({predictions:c.predictions,disagreement:c.model_disagreement},null,2))}</pre></details>
      <details><summary>Developability (separate from thermostability)</summary><pre>${esc(JSON.stringify(c.developability,null,2))}</pre></details>
      <p><strong>Decision</strong>: ${c.rationale.map(esc).join('; ')}</p>
      <ul>${c.uncertainty.concat(c.limitations || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
      ${(c.structures || []).length ? `<h3>Saved structures</h3><p class="muted">Cα trace · drag to rotate · scroll to zoom · chain toggles. No inferred CDR mapping.</p>${c.structures.map((s,i) => `<div id="mol-${i}" class="molecule"></div>`).join('')}${c.reference_structure ? '<h4>Trastuzumab reference (independent frame; not superimposed)</h4><div id="mol-ref" class="molecule"></div>' : ''}` : '<p class="muted">No saved structure. No coordinates have been fabricated.</p>'}
      </section>`;
  }
  async function detail(id) {
    const j = await api('/' + encodeURIComponent(id));
    const signature = JSON.stringify(j);
    if (cache === signature && pageKey === 'detail:' + id) return;
    cache = signature; pageKey = 'detail:' + id;
    const r = j.result, counts = r && r.counts;
    view().innerHTML = `<p><a href="/experiments">← iterations</a></p><h1>${esc(j.spec.question)}</h1>
      <p><code>${esc(j.id)}</code> ${status(j)} · ${esc(j.spec.mode)} · seed ${j.spec.seed}${j.spec.parent ? ` · parent <a href="${url(j.spec.parent)}">${esc(j.spec.parent)}</a>` : ''}</p>
      <p class="muted">Started ${esc(new Date(j.created).toLocaleString())} · updated ${esc(new Date(j.updated).toLocaleString())}</p>
      ${j.error ? `<div class="note bad">${esc(j.error)}</div>` : ''}
      ${counts ? `<div class="cards"><div class="card"><b>${counts.generated}</b><span>candidates</span></div><div class="card"><b>${counts.eligible}</b><span>official passes</span></div><div class="card"><b>${counts.failed}</b><span>official failures</span></div><div class="card"><b>${counts.shortlisted} / 20</b><span>shortlisted</span></div></div>` : `<p>${['queued','running'].includes(j.status) ? 'Worker is processing independently of this page.' : 'This iteration did not complete. Inspect the error and retained partial evidence; a retry creates a new iteration.'}</p>`}
      ${j.status === 'complete' ? `<p><a class="btn" href="/api/experiments/${encodeURIComponent(j.id)}/export" download>Export sequences, CSV, evidence and provenance (ZIP)</a></p>` : ''}
      <details><summary>Pipeline events / errors</summary><pre>${esc(JSON.stringify(j.events,null,2))}</pre></details>
      ${j.partial_result ? `<details><summary>Retained partial candidate evidence (${j.partial_result.candidates.length})</summary><pre>${esc(JSON.stringify(j.partial_result,null,2))}</pre></details>` : ''}
      ${r ? `<p class="muted">Ranking: ${esc(r.ranking_version)} · reference SHA-256 <code>${esc(r.reference_sha256)}</code></p>
      <details><summary>Objective plots</summary>${objectivePlots(r.candidates)}</details>
      <details><summary>Shortlist sequence diversity</summary>${diversityTable(r.diversity)}</details>
      <div class="controls"><input id="candidate-search" placeholder="Filter candidates"><select id="candidate-filter"><option value="">All decisions</option><option value="shortlist">Shortlist</option><option value="needs_evidence">Needs evidence</option><option value="rejected">Rejected</option></select></div>
      <div id="evidence-table" class="panel"></div><div id="candidate-detail"></div>` : ''}`;
    if (!r) return;
    function draw() {
      const q = document.getElementById('candidate-search').value.toLowerCase();
      const decision = document.getElementById('candidate-filter').value;
      const cs = r.candidates.filter(c => (!decision || c.decision === decision) &&
        [c.design_id,c.cdrh3,c.sequence].join(' ').toLowerCase().includes(q)).slice().sort((a,b) => (a.rank || 9999) - (b.rank || 9999));
      document.getElementById('evidence-table').innerHTML = `<table><thead><tr><th>Rank / front</th><th>Candidate</th><th>Validation</th><th>Binding</th><th>Epitope</th><th>Thermostability</th><th>Decision</th><th>Compare</th></tr></thead><tbody>${cs.map(c => `<tr><td>${c.rank || '—'} / ${c.pareto_front || '—'}</td><td><button class="btn" data-candidate="${esc(c.design_id)}">${esc(c.design_id)}</button></td><td>${esc(c.validation.status)}</td>${['binding','epitope','stability'].map(a => `<td>${metric(c.objectives[a])}</td>`).join('')}<td>${esc(c.decision)}</td><td><input type="checkbox" aria-label="Compare ${esc(c.design_id)}" data-pick="${esc(c.design_id)}" ${comparePicks.includes(c.design_id) ? 'checked' : ''}></td></tr>`).join('')}</tbody></table><div id="candidate-compare"></div>`;
      view().querySelectorAll('[data-candidate]').forEach(b => b.onclick = () => { openCandidate = b.dataset.candidate; show(); });
      view().querySelectorAll('[data-pick]').forEach(b => b.onchange = () => {
        comparePicks = comparePicks.filter(x => x !== b.dataset.pick);
        if (b.checked) comparePicks.push(b.dataset.pick); comparePicks = comparePicks.slice(-4); draw();
      });
      const picks = cs.filter(c => comparePicks.includes(c.design_id));
      if (picks.length > 1) {
        document.getElementById('candidate-compare').innerHTML = '<h3>Candidate comparison</h3>' + picks.map(c => `<h4>${esc(c.design_id)} · front ${c.pareto_front || 'unknown'}</h4>${objectiveTable(c)}`).join('');
        // Sequence identity is explicitly shown, independent of metric coverage.
        const comparisonNode = document.getElementById('candidate-compare');
        comparisonNode.innerHTML += '<div class="pairwise-diversity">Computing sequence diversity…</div>';
        api('/' + encodeURIComponent(j.id) + '/diversity?' + picks.map(c => 'candidate=' + encodeURIComponent(c.design_id)).join('&'))
          .then(d => { if (comparisonNode.isConnected) comparisonNode.querySelector('.pairwise-diversity').innerHTML = diversityTable(d.pairs); })
          .catch(e => { if (comparisonNode.isConnected) comparisonNode.querySelector('.pairwise-diversity').textContent = e.message; });
      }
    }
    function show() {
      const c = r.candidates.find(c => c.design_id === openCandidate);
      document.getElementById('candidate-detail').innerHTML = c ? candidate(c,j) : '';
      if (!c) return;
      c.structures.forEach((s,i) => window.AntibodyPDB.mount('mol-' + i,
        '/api/experiments/' + encodeURIComponent(j.id) + '/structure/' + encodeURIComponent(s.path.split('/').pop()), s));
      if (c.reference_structure) window.AntibodyPDB.mount('mol-ref',
        '/api/experiments/' + encodeURIComponent(j.id) + '/structure/' + encodeURIComponent(c.reference_structure.split('/').pop()), {});
    }
    document.getElementById('candidate-search').oninput = draw;
    document.getElementById('candidate-filter').onchange = draw;
    draw(); show();
  }
  async function compare() {
    const d = await api(''); const jobs = d.iterations.filter(j => j.result);
    if (jobs.length < 2) { view().innerHTML = '<h1>Compare iterations</h1><p>Complete two iterations to compare evidence and decisions.</p>'; return; }
    view().innerHTML = `<h1>Compare iterations</h1><p>Compare immutable runs. Different models, units or missing objectives cannot establish improvement.</p><div class="controls">${['left','right'].map((n,i) => `<select id="compare-${n}">${jobs.map((j,k) => `<option value="${esc(j.id)}" ${i===k ? 'selected' : ''}>${esc(j.spec.question)} · ${esc(j.id)}</option>`).join('')}</select>`).join('')}</div><div id="iteration-comparison"></div>`;
    function draw() {
      const js = ['left','right'].map(n => jobs.find(j => j.id === document.getElementById('compare-' + n).value));
      document.getElementById('iteration-comparison').innerHTML = `<div class="compare-grid">${js.map(j => `<section><h2>${esc(j.spec.question)}</h2><p>${esc(j.spec.mode)} · seed ${j.spec.seed} · ${status(j)}</p><pre>${esc(JSON.stringify(j.result.counts,null,2))}</pre><h3>Objective coverage</h3>${['binding','epitope','stability'].map(a => `<p>${a}: ${j.result.candidates.filter(c => c.objectives[a].status === 'available').length} / ${j.result.counts.generated}</p>`).join('')}<h3>Shortlist</h3><ul>${j.result.candidates.filter(c => c.selected).map(c => `<li>${esc(c.design_id)} · front ${c.pareto_front}</li>`).join('') || '<li>No officially eligible shortlist</li>'}</ul><details><summary>Sequence diversity</summary>${diversityTable(j.result.diversity)}</details><a href="${url(j.id)}">Inspect iteration</a></section>`).join('')}</div><h2>Objective plots across iterations</h2>${objectivePlots(js.flatMap(j => j.result.candidates.map(c => ({...c, iteration_label:j.id}))))}`;
    }
    ['left','right'].forEach(n => document.getElementById('compare-' + n).onchange = draw); draw();
  }
  window.antibodyWorkspace = async function (page, id) {
    // Polling must not replace a form, viewer, filters or comparison selection.
    const key = page + ':' + (id || '');
    // Legacy routes share this view and replace its children. A cached job
    // must still render when returning from one of those routes.
    if (!view().querySelector('[data-antibody-workspace]')) { cache = ''; pageKey = ''; }
    if (pageKey === key && (document.querySelector('#new-experiment[open]') || page === 'compare')) return;
    if (pageKey !== key) { cache = ''; pageKey = key; }
    try {
      if (page === 'list') await list(); else if (page === 'detail') await detail(id); else await compare();
      if (!view().querySelector('[data-antibody-workspace]')) {
        const marker = document.createElement('span'); marker.hidden = true;
        marker.dataset.antibodyWorkspace = 'true'; view().append(marker);
      }
    }
    catch(e) { error(e); }
  };
})();
