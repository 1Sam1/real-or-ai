// REAL OR AI backend deployed on Render.
const API_BASE = "https://real-or-ai-api.onrender.com";
const $ = (id) => document.getElementById(id);
let mode = "upload";

function chooseMode(next) {
  mode = next;
  $("uploadPanel").hidden = next !== "upload";
  $("linkPanel").hidden = next !== "link";
  $("uploadTab").classList.toggle("active", next === "upload");
  $("linkTab").classList.toggle("active", next === "link");
  validate();
}

$("uploadTab").addEventListener("click", () => chooseMode("upload"));
$("linkTab").addEventListener("click", () => chooseMode("link"));
$("videoFile").addEventListener("change", () => {
  $("fileName").textContent = $("videoFile").files[0]?.name || "";
  validate();
});
$("videoUrl").addEventListener("input", validate);

function validate() {
  $("analyseBtn").disabled = mode === "upload"
    ? !$("videoFile").files.length
    : !$("videoUrl").value.trim();
}

const key = () => {
  const d = new Date();
  return "real-or-ai-demo-" + d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
};

function updateLimit() {
  const used = Number(localStorage.getItem(key()) || 0);
  $("usageText").textContent = Math.max(0, 3 - used) + " of 3 demo checks remaining today · No account needed";
  if (used >= 3) $("analyseBtn").disabled = true;
}

updateLimit();

$("analyseBtn").addEventListener("click", async () => {
  const used = Number(localStorage.getItem(key()) || 0);
  if (used >= 3) {
    $("status").textContent = "You have reached the three-check demo limit for today.";
    return;
  }

  if (mode !== "upload") {
    $("status").textContent = "Direct social-media link analysis is not available yet. Please upload the original video instead.";
    return;
  }

  const file = $("videoFile").files[0];
  if (!file) {
    $("status").textContent = "Please choose a video first.";
    return;
  }

  $("analyseBtn").disabled = true;
  $("status").textContent = "Checking connection to the analysis server…";

  try {
    // First verify browser-to-Render connectivity and CORS independently of the upload.
    const healthResponse = await fetch(API_BASE + "/health", { method: "GET", cache: "no-store" });
    if (!healthResponse.ok) {
      throw new Error("The analysis server responded with HTTP " + healthResponse.status + ". Please try again shortly.");
    }
    const health = await healthResponse.json();
    if (!health.ok) throw new Error("The analysis service is not ready yet. Please try again shortly.");

    $("status").textContent = "Connection successful. Sending video securely for analysis…";

    const body = new FormData();
    body.append("video", file);
    const res = await fetch(API_BASE + "/api/analyse", { method: "POST", body });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      throw new Error(data.detail || data.error || "Analysis could not be completed (HTTP " + res.status + ").");
    }

    localStorage.setItem(key(), String(used + 1));
    updateLimit();

    $("status").textContent =
      "Assessment: " + (data.verdict || "Uncertain") +
      " · AI probability: " + (data.synthetic_probability ?? "not provided") + "%" +
      " · Confidence: " + (data.confidence ?? "not provided") + "%. " +
      (data.explanation || "");
  } catch (e) {
    const message = e && e.message ? e.message : String(e);
    if (message === "Failed to fetch" || e instanceof TypeError) {
      $("status").textContent = "Browser could not connect to the analysis server. The connection check or upload was blocked. Please send us the exact status message and the Render logs from the same test.";
    } else {
      $("status").textContent = message;
    }
  } finally {
    validate();
    if (Number(localStorage.getItem(key()) || 0) >= 3) $("analyseBtn").disabled = true;
  }
});
