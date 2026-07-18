/* app.js — talks to the FastAPI backend at API_BASE.
   API_BASE comes from config.js (window.APP_CONFIG), so it can be changed
   per environment without editing this file. Falls back to localhost if
   config.js wasn't loaded (e.g. someone forgot to copy config.example.js). */
const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.API_BASE) || "http://127.0.0.1:8000";
const MAX_UPLOAD_MB = 10;                 // keep in sync with backend .env MAX_UPLOAD_SIZE_MB
const ALLOWED_EXTS = [".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff"];

const fileInput   = document.getElementById("file-input");
const dropzone    = document.getElementById("dropzone");
const uploadStatus= document.getElementById("upload-status");

const resultsPanel  = document.getElementById("results-panel");
const chatPanel      = document.getElementById("chat-panel");
const dashboardPanel = document.getElementById("dashboard-panel");

let currentReportId = null;
let trendChart = null;
let isUploading = false;

/* ---------- Upload handling ---------- */

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) uploadReport(fileInput.files[0]);
});

// drag & drop
["dragover", "dragenter"].forEach(evt =>
  dropzone.addEventListener(evt, e => { e.preventDefault(); if (!isUploading) dropzone.style.borderColor = "#2F6F5E"; })
);
["dragleave", "drop"].forEach(evt =>
  dropzone.addEventListener(evt, e => { e.preventDefault(); dropzone.style.borderColor = ""; })
);
dropzone.addEventListener("drop", e => {
  if (isUploading) return;
  const file = e.dataTransfer.files[0];
  if (file) uploadReport(file);
});

function validateFile(file) {
  const ext = "." + file.name.split(".").pop().toLowerCase();
  if (!ALLOWED_EXTS.includes(ext)) {
    return `Unsupported file type '${ext}'. Allowed: ${ALLOWED_EXTS.join(", ")}`;
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `File too large. Max allowed size is ${MAX_UPLOAD_MB}MB.`;
  }
  return null;
}

async function uploadReport(file) {
  const validationError = validateFile(file);
  if (validationError) {
    setStatus(validationError, "error");
    return;
  }

  isUploading = true;
  dropzone.classList.add("is-busy");
  setStatus("Reading your report…", "loading");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok) {
      setStatus(data.detail || "Something went wrong reading that file.", "error");
      return;
    }

    setStatus("Done — see your results below.", "success");
    currentReportId = data.report_id;
    renderResults(data);
    chatPanel.classList.remove("hidden");
    await refreshDashboard();
  } catch (err) {
    setStatus("Couldn't reach the server. Is the backend running? Check API_BASE in js/config.js.", "error");
  } finally {
    isUploading = false;
    dropzone.classList.remove("is-busy");
    fileInput.value = ""; // allow re-uploading the same file name
  }
}

function setStatus(msg, kind) {
  uploadStatus.textContent = msg;
  uploadStatus.className = "status" + (kind ? " " + kind : "");
}

/* ---------- Render results ---------- */

function renderResults(data) {
  resultsPanel.classList.remove("hidden");
  document.getElementById("report-name").textContent = `Results — ${data.filename}`;
  document.getElementById("report-overview").textContent = data.summary.overview;
  document.getElementById("disclaimer-text").textContent = data.disclaimer;

  // Table
  const tbody = document.getElementById("lab-table-body");
  tbody.innerHTML = "";
  data.parameters.forEach(p => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.name}</td>
      <td>${p.value} <span style="color:var(--ink-soft)">${p.unit}</span></td>
      <td>${p.normal_range}</td>
      <td><span class="pill ${p.status.toLowerCase()}">${p.status}</span></td>
    `;
    tbody.appendChild(tr);
  });

  // Explanations
  const explWrap = document.getElementById("explanations");
  explWrap.innerHTML = "";
  data.summary.explanations.forEach(e => {
    const div = document.createElement("div");
    div.className = `explain-item ${e.status.toLowerCase()}`;
    div.innerHTML = `<b>${e.name}</b> — ${e.explanation}`;
    explWrap.appendChild(div);
  });

  // Risks
  const risksList = document.getElementById("risks-list");
  const risksBlock = document.getElementById("risks-block");
  risksList.innerHTML = "";
  if (data.risks.length === 0) {
    risksBlock.classList.add("hidden");
  } else {
    risksBlock.classList.remove("hidden");
    data.risks.forEach(r => {
      const card = document.createElement("div");
      card.className = "risk-card";
      card.innerHTML = `
        <h4>${r.parameter} — ${r.status}</h4>
        <p>${r.risk}</p>
        <ul>${r.suggestions.map(s => `<li>${s}</li>`).join("")}</ul>
      `;
      risksList.appendChild(card);
    });
  }

  // Score dial (circle circumference = 2 * PI * r, r=52 -> 326.7)
  const circumference = 326.7;
  const offset = circumference - (data.health_score / 100) * circumference;
  const dialFill = document.getElementById("dial-fill");
  dialFill.style.strokeDashoffset = offset;
  dialFill.style.stroke = data.health_score >= 70 ? "#2F6F5E" : data.health_score >= 40 ? "#C05621" : "#B3401F";
  document.getElementById("score-value").textContent = data.health_score;
}

/* ---------- Chat ---------- */

const chatForm  = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatLog   = document.getElementById("chat-log");

chatForm.addEventListener("submit", async e => {
  e.preventDefault();
  const question = chatInput.value.trim();
  if (!question) return;

  appendChatMessage(question, "user");
  chatInput.value = "";
  chatInput.disabled = true;
  chatForm.querySelector("button").disabled = true;

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, report_id: currentReportId }),
    });
    const data = await res.json();
    appendChatMessage(res.ok ? data.answer : (data.detail || "Something went wrong."), "bot");
  } catch {
    appendChatMessage("Couldn't reach the server right now.", "bot");
  } finally {
    chatInput.disabled = false;
    chatForm.querySelector("button").disabled = false;
    chatInput.focus();
  }
});

function appendChatMessage(text, who) {
  const div = document.createElement("div");
  div.className = `chat-msg ${who}`;
  div.textContent = text;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
}

/* ---------- Dashboard trend ---------- */

async function refreshDashboard() {
  try {
    const res = await fetch(`${API_BASE}/api/reports`);
    const reports = await res.json();
    if (!reports.length) return;

    dashboardPanel.classList.remove("hidden");
    const labels = reports.map((r, i) => `#${i + 1} · ${r.filename}`);
    const scores = reports.map(r => r.health_score);

    const ctx = document.getElementById("trend-chart").getContext("2d");
    if (trendChart) trendChart.destroy();
    trendChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Wellness score",
          data: scores,
          borderColor: "#2F6F5E",
          backgroundColor: "rgba(47,111,94,0.12)",
          tension: 0.3,
          fill: true,
          pointRadius: 4,
        }],
      },
      options: {
        scales: { y: { min: 0, max: 100 } },
        plugins: { legend: { display: false } },
      },
    });
  } catch {
    /* dashboard is best-effort; ignore errors */
  }
}
