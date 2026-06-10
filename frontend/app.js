const incidentList = document.querySelector("#incident-list");
const incidentTitle = document.querySelector("#incident-title");
const incidentMeta = document.querySelector("#incident-meta");
const incidentConfidence = document.querySelector("#incident-confidence");
const timelineCount = document.querySelector("#timeline-count");
const timeline = document.querySelector("#timeline");
const hypotheses = document.querySelector("#hypotheses");
const actions = document.querySelector("#actions");
const blastRadius = document.querySelector("#blast-radius");
const postmortem = document.querySelector("#postmortem");

function formatTime(value) {
  return new Intl.DateTimeFormat("en", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(new Date(value));
}

function formatPercent(value) {
  return `${Math.round(value * 100)}%`;
}

function text(value) {
  const span = document.createElement("span");
  span.textContent = value;
  return span;
}

function renderIncidentList(incidents, activeIncidentId) {
  incidentList.innerHTML = "";
  incidents.forEach((incident) => {
    const button = document.createElement("button");
    button.className = `incident-button ${incident.id === activeIncidentId ? "active" : ""}`;
    button.type = "button";
    button.dataset.incidentId = incident.id;
    button.innerHTML = `
      <strong>${incident.service}</strong>
      <span>${incident.severity} · ${incident.status.replaceAll("_", " ")}</span>
    `;
    button.addEventListener("click", () => loadAnalysis(incident.id));
    incidentList.append(button);
  });
}

function renderHeader(incident) {
  incidentTitle.textContent = incident.title;
  incidentConfidence.textContent = formatPercent(incident.confidence);
  incidentMeta.innerHTML = "";

  [
    incident.service,
    incident.severity,
    incident.status.replaceAll("_", " "),
    `Started ${formatTime(incident.started_at)}`,
    `Ended ${formatTime(incident.ended_at)}`,
  ].forEach((item) => {
    const pill = document.createElement("span");
    pill.className = "meta-pill";
    pill.textContent = item;
    incidentMeta.append(pill);
  });
}

function renderTimeline(items) {
  timelineCount.textContent = `${items.length} events`;
  timeline.innerHTML = "";

  items.forEach((item) => {
    const row = document.createElement("article");
    row.className = "timeline-item";
    row.innerHTML = `
      <div class="timeline-time">${formatTime(item.timestamp)}</div>
      <div>
        <div class="timeline-title">
          <span>${item.title}</span>
          <span class="severity ${item.severity}">${item.severity}</span>
        </div>
        <p class="timeline-description">${item.description}</p>
        <code class="query">${item.evidence.query}</code>
      </div>
    `;
    timeline.append(row);
  });
}

function renderHypotheses(items) {
  hypotheses.innerHTML = "";

  items.forEach((item) => {
    const article = document.createElement("article");
    article.className = "hypothesis";
    article.innerHTML = `
      <div class="hypothesis-header">
        <div class="hypothesis-title">${item.title}</div>
        <span class="confidence-badge">${formatPercent(item.confidence)}</span>
      </div>
      <p>${item.reasoning}</p>
      <div class="evidence-list">
        ${item.supporting_evidence
          .map((evidence) => `<span class="evidence-chip">${evidence.id}</span>`)
          .join("")}
      </div>
    `;
    hypotheses.append(article);
  });
}

function renderActions(items) {
  actions.innerHTML = "";

  items.forEach((item) => {
    const article = document.createElement("article");
    article.className = "action";
    article.innerHTML = `
      <div class="action-header">
        <div class="action-title">${item.title}</div>
        <span class="priority-badge">${item.priority.toUpperCase()}</span>
      </div>
      <p>${item.rationale}</p>
      <div class="evidence-list">
        <span class="evidence-chip">${item.owner}</span>
        ${item.evidence.map((evidence) => `<span class="evidence-chip">${evidence.id}</span>`).join("")}
      </div>
    `;
    actions.append(article);
  });
}

function renderBlastRadius(radius) {
  blastRadius.innerHTML = `
    <p>${radius.summary}</p>
    <ul class="metric-list">
      <li><strong>Services:</strong> ${radius.impacted_services.join(", ")}</li>
      <li><strong>Regions:</strong> ${radius.impacted_regions.join(", ")}</li>
      <li><strong>Impact:</strong> ${radius.customer_impact}</li>
      ${radius.key_metrics.map((metric) => `<li>${metric}</li>`).join("")}
    </ul>
  `;
}

function renderPostmortem(draft) {
  postmortem.innerHTML = `
    <article class="postmortem-section">
      <h4>Summary</h4>
      <p>${draft.summary}</p>
    </article>
    <article class="postmortem-section">
      <h4>Root Cause</h4>
      <p>${draft.root_cause}</p>
    </article>
    <article class="postmortem-section">
      <h4>Impact and Resolution</h4>
      <p>${draft.impact} ${draft.resolution}</p>
    </article>
    <article class="postmortem-section">
      <h4>Prevention Tasks</h4>
      <ul>${draft.prevention_tasks.map((task) => `<li>${task}</li>`).join("")}</ul>
    </article>
  `;
}

async function loadAnalysis(incidentId) {
  timeline.innerHTML = '<div class="loading">Loading Splunk evidence timeline</div>';
  const response = await fetch(`/api/incidents/${incidentId}/analysis`);
  const analysis = await response.json();

  renderHeader(analysis.incident);
  renderTimeline(analysis.timeline);
  renderHypotheses(analysis.hypotheses);
  renderActions(analysis.recommended_actions);
  renderBlastRadius(analysis.blast_radius);
  renderPostmortem(analysis.postmortem);

  const incidents = await fetch("/api/incidents").then((item) => item.json());
  renderIncidentList(incidents, incidentId);
}

async function init() {
  incidentList.innerHTML = '<div class="loading">Loading incidents</div>';
  const incidents = await fetch("/api/incidents").then((response) => response.json());
  renderIncidentList(incidents, incidents[0].id);
  await loadAnalysis(incidents[0].id);
}

init().catch((error) => {
  incidentTitle.textContent = "Backend unavailable";
  timeline.innerHTML = `<div class="loading">${error.message}</div>`;
});
