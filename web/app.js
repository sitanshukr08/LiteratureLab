'use strict';
const $ = id => document.getElementById(id);
const state = {papers: [], result: null, busy: false};
function el(tag, text, cls) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; }
async function api(path, options = {}) {
  const response = await fetch(path, options);
  let data; try { data = await response.json(); } catch { throw new Error('The server returned an unreadable response.'); }
  if (!response.ok) throw new Error(data.error || data.detail || 'Request failed.');
  return data;
}
function showError(error) { $('error').textContent = error.message; $('error').hidden = false; }
function setBusy(value, message) {
  state.busy = value;
  for (const id of ['ask', 'retrieve', 'upload']) $(id).disabled = value;
  $('research-status').textContent = message;
  $('research-status').classList.toggle('busy', value);
}
function selectedPapers() { return [...document.querySelectorAll('.paper input:checked')].map(n => n.value); }
async function loadPapers() {
  const selected = new Set(selectedPapers());
  state.papers = await api('/api/papers');
  $('paper-count').textContent = state.papers.length;
  $('papers').replaceChildren();
  if (!state.papers.length) $('papers').append(el('p', 'Add a paper to start your library.', 'muted small'));
  for (const paper of state.papers) {
    const row = el('div', undefined, 'paper');
    const checkbox = el('input'); checkbox.type = 'checkbox'; checkbox.value = paper.id; checkbox.id = `paper-${paper.id}`; checkbox.checked = selected.has(paper.id);
    const label = el('label'); label.htmlFor = checkbox.id; label.append(el('span', paper.title, 'paper-title'), el('span', `${paper.pages} pages · ${paper.sections} sections`, 'paper-info'));
    const body = el('div'); body.style.flex = '1'; body.style.minWidth = '0'; body.append(label);
    const actions = el('div', undefined, 'paper-actions');
    const link = el('a', 'Open PDF ↗'); link.href = `/api/papers/${paper.id}/pdf`; link.target = '_blank'; link.rel = 'noopener';
    const remove = el('button', 'Remove'); remove.type = 'button'; remove.setAttribute('aria-label', `Remove ${paper.title}`);
    remove.addEventListener('click', async () => {
      if (state.busy || !confirm(`Remove “${paper.title}” and its indexed evidence from this library?`)) return;
      try { await api(`/api/papers/${paper.id}`, {method: 'DELETE'}); await loadPapers(); }
      catch (error) { showError(error); }
    });
    actions.append(link, remove); body.append(actions); row.append(checkbox, body); $('papers').append(row);
  }
}
async function loadHistory() {
  const notes = await api('/api/history'); $('history').replaceChildren();
  if (!notes.length) $('history').append(el('p', 'Your synthesis notes will appear here.', 'small muted'));
  for (const note of notes.slice(0, 12)) {
    const button = el('button', note.question); button.title = note.question;
    button.addEventListener('click', async () => {
      if (state.busy) return;
      try { const result = await api(`/api/history/${note.id}`); $('question').value = result.question; showView('research'); renderResult(result); $('research-status').textContent = 'Opened a saved research note.'; }
      catch (error) { showError(error); }
    }); $('history').append(button);
  }
}
function renderEvidence(evidence, claims = []) {
  $('evidence').replaceChildren(); $('evidence-count').textContent = evidence.length;
  for (const source of evidence) {
    const card = el('article', undefined, 'evidence-card'); card.id = `source-${source.citation_id}`;
    card.append(el('span', `${source.citation_id} / ${source.level.toUpperCase()}`, 'evidence-label'), el('h3', source.title), el('p', `${source.section} · PDF p. ${source.pages.join(', ')}`));
    const quotes = new Set(claims.flatMap(c => c.evidence).filter(r => r.id === source.citation_id).map(r => r.quote));
    for (const quote of quotes) card.append(el('p', `“${quote}”`, 'evidence-quote'));
    const details = el('details'); details.append(el('summary', 'Read original passage'), el('p', source.text));
    const link = el('a', 'Open source page ↗'); link.href = `/api/papers/${source.paper_id}/pdf#page=${source.pages[0]}`; link.target = '_blank'; link.rel = 'noopener';
    card.append(details, link); $('evidence').append(card);
  }
}
function renderTrace(trace) {
  $('trace-panel').hidden = false; $('trace-content').replaceChildren();
  const grid = el('div', undefined, 'trace-grid');
  const values = [['Strategy', trace.strategy], ['Resolution', trace.resolution], ['Evidence budget', `${trace.evidence_words} / 1600 words`], ['Sources covered', trace.covered_papers.length], ['Coarse / fine vectors', `${trace.coarse_vectors_scored} / ${trace.fine_vectors_scored}`], ['Embedding', `${trace.embedding_ms} ms`], ['Dense / lexical', `${trace.dense_ms} / ${trace.lexical_ms} ms`], ['Total retrieval', `${trace.total_ms} ms`]];
  for (const [label, value] of values) grid.append(el('span', label), el('strong', String(value)));
  $('trace-content').append(grid, el('p', trace.reason, 'small muted'));
  if (trace.fallback) $('trace-content').append(el('p', trace.fallback, 'small muted'));
}
function renderResult(result) {
  state.result = result; $('answer-section').hidden = false; $('empty-guide').hidden = true;
  $('answer-title').textContent = result.claims.length ? 'Draft synthesis · inspect the sources' : 'Evidence is insufficient';
  const tokens = (result.usage.generation.total_tokens || 0) + (result.usage.review.total_tokens || 0);
  $('answer-meta').textContent = `${result.model} · ${result.cached ? 'Cached answer · original ' : ''}${result.duration_seconds}s · ${tokens} tokens · ${new Date(result.created).toLocaleString()}`;
  $('answer-content').replaceChildren();
  if (!result.claims.length) $('answer-content').append(el('p', 'The available passages do not establish an answer. No supported claim was retained.'));
  for (const claim of result.claims) {
    const section = el('div', undefined, 'claim'); section.append(el('span', claim.kind === 'inference' ? 'DRAFT INFERENCE' : 'DRAFT REPORTED FINDING', 'evidence-label'), el('p', claim.text));
    for (const ref of claim.evidence) {
      const button = el('button', `${ref.id} · p. ${ref.pages.join(', ')}`, 'citation'); button.title = `${ref.title}: ${ref.quote}`;
      button.addEventListener('click', () => {
        const target = $(`source-${ref.id}`); target.querySelector('details').open = true;
        target.querySelector('a').href = `/api/papers/${ref.paper_id}/pdf#page=${ref.pages[0]}`;
        target.scrollIntoView({behavior: 'smooth', block: 'nearest'}); target.classList.add('highlight'); setTimeout(() => target.classList.remove('highlight'), 2500);
      }); section.append(button);
    } $('answer-content').append(section);
  }
  $('limitations').replaceChildren();
  if (result.limitations.length || result.insufficient_evidence) {
    const box = el('div', undefined, 'limitations'); box.append(el('strong', 'Evidence limits'));
    for (const text of result.limitations) box.append(el('p', text));
    if (result.insufficient_evidence && result.claims.length) box.append(el('p', 'This question is only partly answered by the retrieved evidence.'));
    $('limitations').append(box);
  }
  $('verification-note').textContent = result.verification_note;
  $('filtered').hidden = !result.rejected_claims.length; $('filtered-content').replaceChildren();
  $('filtered-summary').textContent = `${result.rejected_claims.length} draft claim(s) withheld by validation or support review`;
  for (const rejected of result.rejected_claims) $('filtered-content').append(el('p', `${rejected.text} — ${rejected.reason}`));
  renderEvidence(result.evidence, result.claims); renderTrace(result.trace);
}
async function research(generate) {
  if (state.busy || !$('ask-form').reportValidity()) return;
  $('error').hidden = true;
  state.result = null; $('answer-section').hidden = true; $('trace-panel').hidden = true;
  renderEvidence([]);
  setBusy(true, generate ? 'Retrieving evidence → drafting claims → reviewing support… Free-tier limits may add a wait.' : 'Searching your local paper library…');
  try {
    const result = await api(generate ? '/api/ask' : '/api/search', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question: $('question').value, paper_ids: selectedPapers(), strategy: $('strategy').value})});
    if (generate) { renderResult(result); await loadHistory(); }
    else { state.result = null; $('answer-section').hidden = true; renderEvidence(result.evidence); renderTrace(result.trace); $('trace-panel').open = true; }
    setBusy(false, generate ? 'Synthesis complete. Inspect the cited passages before using a claim.' : 'Retrieval complete. Original evidence is ready to inspect.');
  } catch (error) { showError(error); setBusy(false, 'Request did not complete. Your library is unchanged.'); }
}
$('ask-form').addEventListener('submit', event => { event.preventDefault(); research(true); });
$('retrieve').addEventListener('click', () => research(false));
$('clear-selection').addEventListener('click', () => document.querySelectorAll('.paper input').forEach(n => n.checked = false));
document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => { $('question').value = button.dataset.question; $('question').focus(); }));
$('upload').addEventListener('change', async event => {
  const files = [...event.target.files]; if (!files.length || state.busy) return;
  setBusy(true, 'Extracting sections and indexing your PDFs locally…'); $('error').hidden = true;
  try {
    for (const file of files) {
      if (file.size > 20 * 1024 * 1024) throw new Error(`${file.name} exceeds the 20 MB limit.`);
      $('upload-status').textContent = `Indexing ${file.name}…`;
      const form = new FormData(); form.append('file', file);
      const result = await api('/api/papers', {method: 'POST', body: form});
      $('upload-status').textContent = result.duplicate ? `${file.name} is already indexed.` : `Added ${file.name}.`;
      await loadPapers();
    } setBusy(false, 'Library updated. Ask a question about your papers.');
  } catch (error) { $('upload-status').textContent = 'Upload failed. Check the error below.'; showError(error); setBusy(false, 'Upload stopped. Previously indexed papers are preserved.'); }
  finally { event.target.value = ''; }
});
$('export').addEventListener('click', () => {
  const r = state.result; if (!r) return;
  const lines = [`# ${r.question}`, '', `Model: ${r.model} | Created: ${r.created}`, ''];
  for (const claim of r.claims) { lines.push(`**${claim.kind === 'inference' ? 'Draft inference' : 'Draft reported finding'}:** ${claim.text}`, ''); for (const ref of claim.evidence) lines.push(`- [${ref.id}] ${ref.title}, ${ref.section}, PDF p. ${ref.pages.join(', ')}: “${ref.quote}”`); lines.push(''); }
  lines.push('## Evidence limits', ...r.limitations.map(t => `- ${t}`), '', r.verification_note);
  const url = URL.createObjectURL(new Blob([lines.join('\n')], {type: 'text/markdown'})); const a = el('a'); a.href = url; a.download = `literaturelab-${r.id.slice(0,8)}.md`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
function showView(name) {
  for (const view of ['research', 'evaluation']) { $(`${view}-view`).hidden = view !== name; $(`${view}-tab`).classList.toggle('active', view === name); $(`${view}-tab`).setAttribute('aria-pressed', String(view === name)); }
}
$('research-tab').addEventListener('click', () => showView('research'));
$('evaluation-tab').addEventListener('click', async () => {
  showView('evaluation');
  try {
    const report = await api('/api/evaluation'); const target = $('evaluation-content'); target.replaceChildren();
    if (report.status === 'not-run') { target.append(el('p', 'No evaluation recorded. Run python scripts/evaluate.py from the project folder.', 'eval-note')); return; }
    target.append(el('p', report.scope, 'eval-note'), el('p', `${report.corpus.papers} papers · ${report.corpus.paragraphs} paragraphs · ${report.corpus.sections} section windows · ${report.retrieval_cases} queries`, 'muted small'));
    const table = el('table', undefined, 'eval-table'); const head = el('tr'); for (const label of ['Retriever','Median ms','p95 ms','Paper coverage']) head.append(el('th',label)); table.append(head);
    for (const [strategy, metrics] of Object.entries(report.strategies)) { const row = el('tr'); for (const value of [strategy,metrics.median_ms,metrics.p95_ms,`${metrics.paper_coverage_percent}%`]) row.append(el('td',String(value))); table.append(row); } target.append(table);
    target.append(el('p', report.retrieval_note, 'eval-note'));
    if (report.live_cases) { target.append(el('h2', 'Live Groq checks')); for (const item of report.live_cases) { const row = el('div', undefined, 'eval-live'); row.append(el('h3',item.question),el('p',item.error || `${item.claims} retained claims · ${item.rejected} withheld · ${item.seconds}s · ${item.insufficient_evidence ? 'insufficient evidence flagged' : 'answered'}`)); target.append(row); } }
  } catch (error) { const message = el('div', error.message, 'error'); message.setAttribute('role', 'alert'); $('evaluation-content').replaceChildren(message); }
});
async function initialize() {
  try { const status = await api('/api/status'); $('connection').textContent = status.key_configured ? 'Groq configured · Local workspace' : 'Groq key missing'; await Promise.all([loadPapers(), loadHistory()]); }
  catch (error) { $('connection').textContent = 'Server unavailable'; showError(error); }
}
initialize();
