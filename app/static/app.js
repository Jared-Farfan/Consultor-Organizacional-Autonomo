let investigationId = null;
const $ = (id) => document.getElementById(id);
const money = (value) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value || 0);
const percent = (value) => `${((value || 0) * 100).toFixed(1)}%`;
const categoryLabels = {
  cumplimiento_regulatorio: 'Regulatory compliance',
  deuda_tecnica_critica: 'Critical technical debt',
  mantenimiento_operativo: 'Operational maintenance',
  onboarding_cliente: 'Customer onboarding',
  retencion_clientes: 'Customer retention',
  soporte_reactivo: 'Reactive support',
};
const criticalityLabels = { alto: 'High', medio: 'Medium', bajo: 'Low' };

function setStatus(message, error = false) { const node = $('status'); node.textContent = message; node.style.color = error ? '#bc4a4a' : ''; }
function metric(label, value) { return `<article class="metric"><div class="label">${label}</div><div class="value">${value}</div></article>`; }
function escapeHtml(value) { return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;'); }
function inlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>');
}
function tableCells(line) { return line.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim()); }
function isTableDivider(line) { return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line); }
function renderMarkdown(source) {
  const lines = String(source || '').replaceAll('\r', '').split('\n');
  const html = []; let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim() || /^---+$/.test(line.trim())) { index += 1; continue; }
    if (line.includes('|') && index + 1 < lines.length && isTableDivider(lines[index + 1])) {
      const headers = tableCells(line); index += 2; const rows = [];
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) { rows.push(tableCells(lines[index])); index += 1; }
      html.push(`<table><thead><tr>${headers.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join('')}</tr></thead><tbody>${rows.map((row) => `<tr>${headers.map((_, cell) => `<td>${inlineMarkdown(row[cell] || '')}</td>`).join('')}</tr>`).join('')}</tbody></table>`);
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) { const level = heading[1].length; html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`); index += 1; continue; }
    if (/^[-*]\s+/.test(line)) {
      const items = []; while (index < lines.length && /^[-*]\s+/.test(lines[index])) { items.push(lines[index].replace(/^[-*]\s+/, '')); index += 1; }
      html.push(`<ul>${items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join('')}</ul>`); continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const items = []; while (index < lines.length && /^\d+\.\s+/.test(lines[index])) { items.push(lines[index].replace(/^\d+\.\s+/, '')); index += 1; }
      html.push(`<ol>${items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join('')}</ol>`); continue;
    }
    const paragraph = [line.trim()]; index += 1;
    while (index < lines.length && lines[index].trim() && !/^(#{1,3})\s+|^[-*]\s+|^\d+\.\s+/.test(lines[index]) && !/^---+$/.test(lines[index].trim())) { paragraph.push(lines[index].trim()); index += 1; }
    html.push(`<p>${inlineMarkdown(paragraph.join(' '))}</p>`);
  }
  return html.join('');
}

async function loadStatus() {
  try {
    const response = await fetch('/config/status'); const config = await response.json();
    $('environment').textContent = `${config.environment} / ${config.data_source} / LLM ${config.llm_enabled ? 'ON' : 'OFF'}`;
  } catch { $('environment').textContent = 'API UNAVAILABLE'; }
}

function render(report, trace) {
  const summary = report.executive_summary;
  $('metrics').innerHTML = [
    metric('Tickets analyzed', report.flow_metrics.ticket_count.toLocaleString('en-US')),
    metric('Average lead time', `${report.flow_metrics.avg_lead_hours}h`),
    metric('Average queue time', `${report.flow_metrics.avg_queue_hours}h`),
    metric('Capacity outside core', `${summary.capacity_outside_core_pct}%`),
    metric('Estimated annual cost', money(summary.estimated_annual_cost)),
  ].join('');
  $('alignment').innerHTML = report.effort_value_matrix.rows.map((row) => `<div class="matrix-row"><span>${categoryLabels[row.category] || row.category.replaceAll('_', ' ')}</span><div class="bar"><span style="width:${row.capacity_share * 100}%"></span></div><span class="badge">${percent(row.capacity_share)} / ${criticalityLabels[row.strategic_criticality] || row.strategic_criticality}</span></div>`).join('');
  $('handoffs').innerHTML = report.handoff_graph.team_edges.slice(0, 6).map((edge) => `<div class="handoff"><span>${edge.from_team}</span><span class="arrow">-></span><span>${edge.to_team}</span><strong>${edge.handoffs}</strong></div>`).join('') || '<p>No handoffs observed.</p>';
  const findings = Object.values(report.recommendations_by_severity).flat();
  $('findings').innerHTML = findings.map((finding) => `<article class="finding ${finding.severity}"><div class="meta"><span class="chip">${finding.severity}</span><span class="chip">${finding.horizon}</span><span class="chip">${money(finding.annual_cost)}</span></div><h3>${finding.title}</h3><p>${finding.recommendation}</p><p>${finding.evidence[0]}</p></article>`).join('');
  $('horizons').innerHTML = report.horizon_cascade.map((item) => `<article class="horizon"><h3>${item.horizon} / ${item.window}</h3><p>${item.action}</p><p class="gate">Gate: ${item.advance_gate}</p><p>Projected lead time: ${item.scenario.projected_lead_hours}h</p></article>`).join('');
  $('trace').innerHTML = trace.map((step) => `<li><strong>${step.tool}</strong><span>${step.hypothesis}</span><br>${step.conclusion}</li>`).join('');
  $('dashboard').hidden = false;
}

function storeInvestigation(data) {
  investigationId = data.id;
  render(data.report, data.trace);
}

$('investigate').addEventListener('click', async () => {
  const hourly_cost = Number($('hourly-cost').value);
  const label = $('investigation-label').value.trim();
  setStatus('Running deterministic tools and simulations...');
  $('investigate').disabled = true;
  try {
    const response = await fetch('/investigations', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({hourly_cost, label}) });
    const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Could not create the investigation');
    storeInvestigation(data); setStatus(`Investigation completed with ${data.report.executive_summary.findings} findings. Creating another diagnosis replaces this result.`);
  } catch (error) { setStatus(error.message, true); } finally { $('investigate').disabled = false; }
});

$('question-form').addEventListener('submit', async (event) => {
  event.preventDefault(); if (!investigationId) return setStatus('Start an investigation before asking a question.', true);
  const question = $('question').value; setStatus('Reviewing calculated evidence...');
  try {
    const response = await fetch(`/investigations/${investigationId}/questions`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question}) });
    const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Could not answer the question');
    $('answer').hidden = false; $('answer').innerHTML = `${renderMarkdown(data.answer)}<span class="chip">${escapeHtml(data.mode)}</span> <span class="chip">confidence ${escapeHtml(data.confidence)}</span>`; setStatus('Evidence-based answer available.');
  } catch (error) { setStatus(error.message, true); }
});

loadStatus();
