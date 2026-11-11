import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

APP_DIR = Path(__file__).resolve().parent
NVIDIA_CLIENT = APP_DIR / "nim-clients" / "synthetic-video-detector" / "scripts" / "v1" / "synthetic-video-detector.py"
NVIDIA_FUNCTION_ID = "847b6e53-0133-452d-ab85-d7acf3ace723"
NVIDIA_TARGET = "grpc.nvcf.nvidia.com:443"
MAX_VIDEO_BYTES = 50 * 1024 * 1024
CLASSIFICATION_THRESHOLD = 0.30

app = FastAPI(title="REAL OR AI API", version="0.1.0")
logger = logging.getLogger("real_or_ai")

allowed_origin = os.getenv("ALLOWED_ORIGIN", "https://1sam1.github.io")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[allowed_origin],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def root():
    return {"service": "REAL OR AI API", "status": "online", "detector": "NVIDIA Synthetic Video Detector"}


@app.get("/health")
def health():
    return {
        "ok": True,
        "nvidia_key_configured": bool(os.getenv("NVIDIA_API_KEY")),
        "nvidia_client_installed": NVIDIA_CLIENT.is_file(),
    }


@app.post("/api/analyse")
async def analyse(video: UploadFile = File(...)):
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="The video analysis service is not configured yet.")
    if not NVIDIA_CLIENT.is_file():
        raise HTTPException(status_code=503, detail="The NVIDIA client is not installed on the server.")

    filename = (video.filename or "").lower()
    if not filename.endswith(".mp4"):
        raise HTTPException(status_code=415, detail="Please upload an MP4 video encoded with H.264.")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="real-or-ai-", suffix=".mp4", delete=False) as tmp:
            temp_path = Path(tmp.name)
            total = 0
            first_bytes = b""
            while True:
                chunk = await video.read(1024 * 1024)
                if not chunk:
                    break
                if not first_bytes:
                    first_bytes = chunk[:16]
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    raise HTTPException(status_code=413, detail="The current upload limit is 50 MB.")
                tmp.write(chunk)

        if total < 16 or first_bytes[4:8] != b"ftyp":
            raise HTTPException(status_code=415, detail="This does not appear to be a valid MP4 video.")

        command = [
            sys.executable,
            str(NVIDIA_CLIENT),
            "--preview-mode",
            "--target", NVIDIA_TARGET,
            "--function-id", NVIDIA_FUNCTION_ID,
            "--api-key", api_key,
            "--video-input", str(temp_path),
        ]

        try:
            result = subprocess.run(
                command,
                cwd=str(NVIDIA_CLIENT.parent),
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="The video analysis timed out. Please try a shorter video.")

        output = (result.stdout or "") + "\n" + (result.stderr or "")
        probability_match = re.search(r"Final probability:\s*([0-9]*[.]?[0-9]+)", output)
        frames_match = re.search(r"Total frames processed:\s*(\d+)", output)

        if result.returncode != 0 or not probability_match:
            # Log useful diagnostics on the server, but never expose the API key.
            safe_output = output.replace(api_key, "[REDACTED]")[-5000:]
            logger.error(
                "NVIDIA detector failed (exit=%s). Output tail:\\n%s",
                result.returncode,
                safe_output,
            )
            if "UNAUTHENTICATED" in output or "PERMISSION_DENIED" in output:
                message = "NVIDIA rejected the API credentials or this account does not have access to the detector."
            elif "UNAVAILABLE" in output or "DEADLINE_EXCEEDED" in output:
                message = "NVIDIA's analysis service is unavailable or timed out. Please try again later."
            elif "No module named" in output or "ModuleNotFoundError" in output:
                message = "The NVIDIA client is missing a required Python package. The server log has the exact package error."
            elif "Configuration error" in output or "unrecognized arguments" in output:
                message = "The NVIDIA client configuration or command-line options are incorrect. The server log has the exact error."
            elif not probability_match and result.returncode == 0:
                message = "The detector ran but did not return a readable probability. The server log has the output for diagnosis."
            else:
                message = "NVIDIA analysis failed. The server log now contains the detailed error; please share that log with support."
            raise HTTPException(status_code=502, detail=message)

        probability = float(probability_match.group(1))
        probability = max(0.0, min(1.0, probability))
        synthetic = probability > CLASSIFICATION_THRESHOLD
        verdict = "LIKELY AI-GENERATED" if synthetic else "LIKELY HUMAN-MADE"
        confidence = probability * 100 if synthetic else (1.0 - probability) * 100

        return {
            "verdict": verdict,
            "synthetic_probability": round(probability * 100, 2),
            "confidence": round(confidence, 2),
            "threshold": CLASSIFICATION_THRESHOLD,
            "frames_processed": int(frames_match.group(1)) if frames_match else None,
            "explanation": "This is a probabilistic model assessment, not proof of authenticity. False positives and false negatives are possible.",
        }
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        await video.close()
