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
    $("status").textContent = "Direct social-media link analysis is not available yet. Please download the video where permitted and upload the MP4 file instead.";
    return;
  }

  const file = $("videoFile").files[0];
  if (!file) {
    $("status").textContent = "Please choose an MP4 video first.";
    return;
  }

  if (!file.name.toLowerCase().endsWith(".mp4")) {
    $("status").textContent = "Please upload an MP4 video encoded with H.264.";
    return;
  }

  $("analyseBtn").disabled = true;
  $("status").textContent = "Sending video securely for analysis. This may take a few minutes…";

  try {
    const body = new FormData();
    body.append("video", file);
    const res = await fetch(API_BASE + "/api/analyse", { method: "POST", body });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      throw new Error(data.detail || data.error || "Analysis could not be completed. Please try again.");
    }

    localStorage.setItem(key(), String(used + 1));
    updateLimit();

    $("status").textContent =
      "Assessment: " + (data.verdict || "Uncertain") +
      " · AI probability: " + (data.synthetic_probability ?? "not provided") + "%" +
      " · Confidence: " + (data.confidence ?? "not provided") + "%. " +
      (data.explanation || "");
  } catch (e) {
    $("status").textContent = e.message || "Something went wrong. Please try again.";
  } finally {
    validate();
    if (Number(localStorage.getItem(key()) || 0) >= 3) $("analyseBtn").disabled = true;
  }
});
