/* ── DOM refs ────────────────────────────────────────────── */
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const dropzoneLabel = document.getElementById("dropzone-label");
const btnExtract = document.getElementById("btn-extract");
const btnSchedule = document.getElementById("btn-schedule");
const btnAuth = document.getElementById("btn-auth");
const btnClear = document.getElementById("btn-clear");
const spinner = document.getElementById("spinner");
const spinnerLabel = document.getElementById("spinner-label");
const toast = document.getElementById("toast");
const resultsCard = document.getElementById("results-card");
const eventsBody = document.getElementById("events-body");
const eventCount = document.getElementById("event-count");
const authStatus = document.getElementById("auth-status");

const API = ""; // same origin — FastAPI serves this page
let selectedFile = null;
let isAuthenticated = false;

/* ── File selection ──────────────────────────────────────── */
dropzone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => handleFile(fileInput.files[0]));

dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("drag-over");
});
dropzone.addEventListener("dragleave", () =>
  dropzone.classList.remove("drag-over"),
);
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("drag-over");
  handleFile(e.dataTransfer.files[0]);
});

function handleFile(file) {
  if (!file) return;
  selectedFile = file;
  dropzoneLabel.textContent = `📎 ${file.name}  (${formatBytes(file.size)})`;
  dropzone.classList.add("has-file");
  btnExtract.disabled = false;
  btnSchedule.disabled = !isAuthenticated;
  hideResults();
}

/* ── Auth ────────────────────────────────────────────────── */
btnAuth.addEventListener("click", async () => {
  btnAuth.disabled = true;
  showSpinner("Opening Google sign-in…");
  try {
    const res = await fetch(`${API}/auth`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Auth failed");
    isAuthenticated = true;
    setAuthBadge(true, data.email || "");
    if (selectedFile) btnSchedule.disabled = false;
    showToast(
      `Authenticated as ${data.email || "Google Calendar"} \u2713`,
      "success",
    );
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    hideSpinner();
    btnAuth.disabled = false;
  }
});

/* ── Extract ─────────────────────────────────────────────── */
btnExtract.addEventListener("click", async () => {
  if (!selectedFile) return;
  showSpinner(
    "Uploading file and extracting with Gemini AI… (may take 15–30 s)",
  );
  setButtons(false);

  try {
    const form = new FormData();
    form.append("file", selectedFile);

    const res = await fetch(`${API}/extract`, { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Extraction failed");

    renderEvents(data.events);
    showToast(
      `Found ${data.count} event${data.count !== 1 ? "s" : ""}`,
      "success",
    );
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    hideSpinner();
    setButtons(true);
  }
});

/* ── Schedule ────────────────────────────────────────────── */
btnSchedule.addEventListener("click", async () => {
  if (!selectedFile) return;
  showSpinner(
    "Extracting with Gemini AI and adding to Google Calendar… (may take 15–30 s)",
  );
  setButtons(false);

  try {
    const form = new FormData();
    form.append("file", selectedFile);

    const res = await fetch(`${API}/schedule`, { method: "POST", body: form });
    const data = await res.json();

    if (res.status === 401) {
      isAuthenticated = false;
      setAuthBadge(false, "");
      btnSchedule.disabled = true;
      showToast("Please click 'Connect Google Calendar' first.", "error");
      return;
    }
    if (!res.ok) throw new Error(data.detail || "Scheduling failed");

    renderEvents(data.events);
    showToast(data.message, "success");
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    hideSpinner();
    setButtons(true);
  }
});

/* ── Clear ───────────────────────────────────────────────── */
btnClear.addEventListener("click", () => {
  selectedFile = null;
  fileInput.value = "";
  dropzoneLabel.textContent = "Drag & drop a file, or click to browse";
  dropzone.classList.remove("has-file");
  btnExtract.disabled = true;
  btnSchedule.disabled = true;
  hideResults();
});

/* ── Render table ────────────────────────────────────────── */
function renderEvents(events) {
  eventsBody.innerHTML = "";
  events.forEach((e) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="day-pill">${esc(e.day)}</span></td>
      <td>${esc(e.start_time)}</td>
      <td>${esc(e.end_time)}</td>
      <td><strong>${esc(e.title)}</strong></td>
      <td>${esc(e.slot || "—")}</td>
      <td>${esc(e.venue || "—")}</td>
    `;
    eventsBody.appendChild(tr);
  });
  eventCount.textContent = events.length;
  resultsCard.classList.remove("hidden");
}

function hideResults() {
  resultsCard.classList.add("hidden");
  eventsBody.innerHTML = "";
}

/* ── Spinner helpers ─────────────────────────────────────── */
function showSpinner(msg) {
  spinnerLabel.textContent = msg;
  spinner.classList.remove("hidden");
}
function hideSpinner() {
  spinner.classList.add("hidden");
}

/* ── Toast ───────────────────────────────────────────────── */
let toastTimer;
function showToast(msg, type = "success") {
  clearTimeout(toastTimer);
  toast.textContent = msg;
  toast.className = `toast toast--${type}`;
  toast.classList.remove("hidden");
  toastTimer = setTimeout(() => toast.classList.add("hidden"), 4000);
}

/* ── Auth badge + button ─────────────────────────────────── */
function setAuthBadge(on, email = "") {
  authStatus.textContent = on ? "Authenticated" : "Not authenticated";
  authStatus.className = `badge badge--${on ? "on" : "off"}`;

  if (on && email) {
    btnAuth.textContent = `\u2713 ${email}`;
    btnAuth.className = "btn btn--connected";
  } else {
    btnAuth.textContent = "Connect Google Calendar";
    btnAuth.className = "btn btn--outline";
  }
}

/* ── Utils ───────────────────────────────────────────────── */
function setButtons(enabled) {
  btnExtract.disabled = !enabled;
  // Schedule button is only re-enabled when authenticated AND a file is selected
  btnSchedule.disabled = !enabled || !isAuthenticated || !selectedFile;
}

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

/* ── Check auth status on load ───────────────────────────── */
(async () => {
  try {
    const res = await fetch(`${API}/auth/status`);
    if (!res.ok) return;
    const data = await res.json();
    isAuthenticated = data.authenticated;
    setAuthBadge(isAuthenticated, data.email || "");
    if (isAuthenticated && selectedFile) btnSchedule.disabled = false;
  } catch {
    /* server not reachable — silently ignore */
  }
})();
