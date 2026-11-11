// REAL OR AI — upload analysis and safe video-link guidance.
const API_BASE = "https://real-or-ai-api.onrender.com";
const $ = (id) => document.getElementById(id);
let mode = "upload";

const VIDEO_PLATFORMS = [
  { name: "YouTube", hosts: ["youtube.com", "youtu.be", "youtube-nocookie.com"] },
  { name: "Instagram", hosts: ["instagram.com"] },
  { name: "Facebook", hosts: ["facebook.com", "fb.watch"] },
  { name: "TikTok", hosts: ["tiktok.com"] },
  { name: "X", hosts: ["x.com", "twitter.com"] }
];

function identifyVideoLink(raw) {
  let url;
  try {
    url = new URL(raw.trim());
  } catch {
    return { valid: false, message: "Please paste a complete video link beginning with https://." };
  }

  if (!["https:", "http:"].includes(url.protocol)) {
    return { valid: false, message: "Only normal web links (https:// or http://) are accepted." };
  }
  if (!url.hostname || url.username || url.password) {
    return { valid: false, message: "That does not look like a valid public video link." };
  }

  const host = url.hostname.toLowerCase().replace(/^www\./, "");
  const platform = VIDEO_PLATFORMS.find(item =>
    item.hosts.some(domain => host === domain || host.endsWith("." + domain))
  );

  if (platform) {
    return {
      valid: true,
      platform: platform.name,
      url: url.href,
      direct: false
    };
  }

  const directVideo = /\.(mp4|mov|m4v|webm)(?:$)/i.test(url.pathname);
  if (directVideo) {
    return { valid: true, platform: "Direct video file", url: url.href, direct: true };
  }

  return {
    valid: false,
    message: "We recognise YouTube, Instagram, Facebook, TikTok and X links, or a direct MP4/MOV/WEBM file link."
  };
}

function chooseMode(next) {
  mode = next;
  $("uploadPanel").hidden = next !== "upload";
  $("linkPanel").hidden = next !== "link";
  $("uploadTab").classList.toggle("active", next === "upload");
  $("linkTab").classList.toggle("active", next === "link");
  $("status").textContent = "";
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
  const canProceed = mode === "upload"
    ? !!$("videoFile").files.length
    : identifyVideoLink($("videoUrl").value).valid;
  $("analyseBtn").disabled = !canProceed;
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

async function analyseUploadedFile(file, used) {
  $("status").textContent = "Checking connection to the analysis server…";
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
}

$("analyseBtn").addEventListener("click", async () => {
  const used = Number(localStorage.getItem(key()) || 0);
  if (used >= 3) {
    $("status").textContent = "You have reached the three-check demo limit for today.";
    return;
  }

  if (mode === "link") {
    const link = identifyVideoLink($("videoUrl").value);
    if (!link.valid) {
      $("status").textContent = link.message;
      return;
    }

    if (!link.direct) {
      $("status").textContent =
        link.platform + " link recognised. This platform does not provide REAL OR AI with a reliably downloadable original video through its public link. To avoid bypassing platform restrictions or giving you a made-up result, open the video, save/download it where permitted, then use “Upload video”.";
      return;
    }

    $("status").textContent =
      "Direct video link recognised. The current analysis server accepts video uploads; direct-link downloading is being added separately. Please upload this video file for a real analysis.";
    return;
  }

  const file = $("videoFile").files[0];
  if (!file) {
    $("status").textContent = "Please choose a video first.";
    return;
  }

  $("analyseBtn").disabled = true;
  try {
    await analyseUploadedFile(file, used);
  } catch (e) {
    const message = e && e.message ? e.message : String(e);
    if (message === "Failed to fetch" || e instanceof TypeError) {
      $("status").textContent = "Browser could not connect to the analysis server. Please try again shortly; if it continues, share the Render logs from the same test.";
    } else {
      $("status").textContent = message;
    }
  } finally {
    validate();
    if (Number(localStorage.getItem(key()) || 0) >= 3) $("analyseBtn").disabled = true;
  }
});
