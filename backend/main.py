import asyncio
import ipaddress
import logging
import socket
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import imageio_ffmpeg
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.datastructures import UploadFile as StarletteUploadFile

APP_DIR = Path(__file__).resolve().parent
NVIDIA_CLIENT = APP_DIR / "nim-clients" / "synthetic-video-detector" / "scripts" / "v1" / "synthetic-video-detector.py"
NVIDIA_FUNCTION_ID = "847b6e53-0133-452d-ab85-d7acf3ace723"
NVIDIA_TARGET = "grpc.nvcf.nvidia.com:443"

# Conservative limits for Render's 512 MB free instance.
MAX_VIDEO_BYTES = 25 * 1024 * 1024
MAX_VIDEO_SECONDS = 60
CLASSIFICATION_THRESHOLD = 0.30
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp"}
ANALYSIS_LOCK = asyncio.Lock()

app = FastAPI(title="REAL OR AI API", version="0.3.0")
logger = logging.getLogger("real_or_ai")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


def limited_subprocess_env():
    """Keep numerical libraries from creating large thread pools."""
    env = os.environ.copy()
    env.update({
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "MPLBACKEND": "Agg",
    })
    return env


def get_video_duration(ffmpeg, input_path):
    # ffmpeg prints the container duration while probing; exit code 1 is
    # expected because this command intentionally has no output destination.
    try:
        probe = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(input_path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env=limited_subprocess_env(),
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=422, detail="The video could not be checked quickly. Please try another file.")

    probe_text = (probe.stderr or "") + "\n" + (probe.stdout or "")
    match = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)", probe_text)
    if not match:
        raise HTTPException(status_code=415, detail="The video duration could not be read. Please upload a standard MP4 or MOV video.")

    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


@app.get("/")
def root():
    return {"service": "REAL OR AI API", "status": "online", "detector": "NVIDIA Synthetic Video Detector"}


@app.get("/health")
def health():
    return {
        "ok": True,
        "nvidia_key_configured": bool(os.getenv("NVIDIA_API_KEY")),
        "nvidia_client_installed": NVIDIA_CLIENT.is_file(),
        "video_normalizer_installed": bool(imageio_ffmpeg.get_ffmpeg_exe()),
        "low_memory_limits": {
            "max_upload_mb": MAX_VIDEO_BYTES // (1024 * 1024),
            "max_video_seconds": MAX_VIDEO_SECONDS,
            "max_parallel_analyses": 1,
            "output_resolution": "up to 854x480",
            "output_fps": 15,
        },
    }



class VideoURLRequest(BaseModel):
    url: str


def validate_public_video_url(raw_url):
    """Allow only public HTTPS direct-video URLs; block private/internal targets."""
    try:
        parsed = urlparse(raw_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Only public HTTPS video links are accepted.")
        if parsed.port not in (None, 443):
            raise ValueError("Non-standard URL ports are not accepted.")
        host = parsed.hostname.encode("idna").decode("ascii")
        if not re.search(r"\.(mp4|mov|m4v|webm)$", parsed.path, re.IGNORECASE):
            raise ValueError("Please use a direct MP4, MOV, M4V or WEBM video-file link.")
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError("The video host could not be resolved.")
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise ValueError("Links to private or internal network addresses are blocked.")
        return parsed, host
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Invalid video URL.")


async def download_direct_video(raw_url, destination):
    current_url = raw_url
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, read=45.0), follow_redirects=False) as client:
        for redirect_count in range(4):
            parsed, host = validate_public_video_url(current_url)
            try:
                async with client.stream("GET", current_url, headers={"User-Agent": "REAL-OR-AI-video-checker/1.0", "Accept": "video/*,application/octet-stream"}) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location or redirect_count == 3:
                            raise HTTPException(status_code=400, detail="The video link redirected too many times or had an invalid redirect.")
                        current_url = urljoin(current_url, location)
                        continue
                    if response.status_code != 200:
                        raise HTTPException(status_code=400, detail=f"The video host returned HTTP {response.status_code}. The file may be private or unavailable.")
                    content_type = response.headers.get("content-type", "").split(";")[0].lower()
                    if content_type and not (content_type.startswith("video/") or content_type == "application/octet-stream"):
                        raise HTTPException(status_code=415, detail="That link did not return a video file. Please use a direct video-file URL.")
                    length = response.headers.get("content-length")
                    if length and int(length) > MAX_VIDEO_BYTES:
                        raise HTTPException(status_code=413, detail="The direct video link exceeds the 25 MB limit.")
                    total = 0
                    with open(destination, "wb") as output:
                        async for chunk in response.aiter_bytes(256 * 1024):
                            total += len(chunk)
                            if total > MAX_VIDEO_BYTES:
                                raise HTTPException(status_code=413, detail="The direct video link exceeds the 25 MB limit.")
                            output.write(chunk)
                    if total < 16:
                        raise HTTPException(status_code=415, detail="The linked video file is empty or too small.")
                    return Path(parsed.path).suffix.lower() or ".mp4"
            except httpx.TimeoutException:
                raise HTTPException(status_code=504, detail="Downloading the video link timed out. Please upload the video instead.")
            except httpx.RequestError:
                raise HTTPException(status_code=400, detail="The video link could not be reached. It may require a login or block downloads.")
    raise HTTPException(status_code=400, detail="The video link could not be followed safely.")


@app.post("/api/analyse-url")
async def analyse_url(request: VideoURLRequest):
    # Only direct public video-file URLs are fetched. Social-media pages are not scraped.
    input_path = None
    wrapped_upload = None
    try:
        parsed, _ = validate_public_video_url(request.url)
        with tempfile.NamedTemporaryFile(prefix="real-or-ai-url-", suffix=".download", delete=False) as tmp:
            input_path = Path(tmp.name)
        extension = await download_direct_video(request.url, input_path)
        handle = open(input_path, "rb")
        wrapped_upload = StarletteUploadFile(filename="linked-video" + extension, file=handle)
        return await analyse(video=wrapped_upload)
    finally:
        if wrapped_upload is not None:
            await wrapped_upload.close()
        if input_path and input_path.exists():
            input_path.unlink(missing_ok=True)

@app.post("/api/analyse")
async def analyse(video: UploadFile = File(...)):
    # A single NVIDIA/FFmpeg job at a time helps avoid overlapping memory peaks.
    if ANALYSIS_LOCK.locked():
        raise HTTPException(status_code=429, detail="Another video is being analysed. Please wait a moment and try again.")

    await ANALYSIS_LOCK.acquire()
    input_path = None
    normalized_path = None
    api_key = os.getenv("NVIDIA_API_KEY")

    try:
        if not api_key:
            raise HTTPException(status_code=503, detail="The video analysis service is not configured yet.")
        if not NVIDIA_CLIENT.is_file():
            raise HTTPException(status_code=503, detail="The NVIDIA client is not installed on the server.")

        original_name = Path(video.filename or "upload.mp4").name
        extension = Path(original_name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=415, detail="Please upload MP4, MOV, M4V, MKV, WEBM, AVI or 3GP video.")

        # Stream the upload to disk in small chunks rather than loading it into RAM.
        with tempfile.NamedTemporaryFile(prefix="real-or-ai-input-", suffix=extension, delete=False) as tmp:
            input_path = Path(tmp.name)
            total = 0
            while True:
                chunk = await video.read(256 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    raise HTTPException(status_code=413, detail="The low-memory upload limit is 25 MB. Please use a smaller video.")
                tmp.write(chunk)

        if total < 16:
            raise HTTPException(status_code=415, detail="The uploaded video is empty or too small to analyse.")

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        duration = get_video_duration(ffmpeg, input_path)
        if duration > MAX_VIDEO_SECONDS:
            raise HTTPException(
                status_code=413,
                detail="For reliable processing on the free server, videos must be 60 seconds or shorter.",
            )

        with tempfile.NamedTemporaryFile(prefix="real-or-ai-ready-", suffix=".mp4", delete=False) as tmp:
            normalized_path = Path(tmp.name)

        # Drop audio and normalize to a small, constant-frame-rate H.264 video.
        # One FFmpeg thread and 480p/15fps output reduce peak memory use.
        conversion = [
            ffmpeg,
            "-hide_banner", "-loglevel", "error", "-y",
            "-threads", "1", "-filter_threads", "1", "-filter_complex_threads", "1",
            "-i", str(input_path),
            "-map", "0:v:0", "-an",
            "-vf", "scale='min(854,iw)':'min(480,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps=15",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-pix_fmt", "yuv420p", "-threads", "1",
            "-r", "15", "-fps_mode", "cfr",
            "-movflags", "+faststart", "-f", "mp4", str(normalized_path),
        ]

        try:
            converted = subprocess.run(
                conversion,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
                env=limited_subprocess_env(),
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=422, detail="This video took too long to prepare. Please try a shorter video.")

        if converted.returncode != 0 or not normalized_path.exists() or normalized_path.stat().st_size < 1024:
            safe_error = (converted.stderr or "No video stream could be decoded.")[-1500:]
            logger.warning("Video conversion failed: %s", safe_error)
            raise HTTPException(status_code=415, detail="This video could not be converted. Please try a different MP4 or MOV file.")

        command = [
            sys.executable,
            str(NVIDIA_CLIENT),
            "--preview-mode",
            "--target", NVIDIA_TARGET,
            "--function-id", NVIDIA_FUNCTION_ID,
            "--api-key", api_key,
            "--video-input", str(normalized_path),
        ]

        try:
            result = subprocess.run(
                command,
                cwd=str(NVIDIA_CLIENT.parent),
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
                env=limited_subprocess_env(),
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="The video analysis timed out. Please try again with a shorter video.")

        output = (result.stdout or "") + "\n" + (result.stderr or "")
        probability_match = re.search(r"Final probability:\s*([0-9]*[.]?[0-9]+)", output)
        frames_match = re.search(r"Total frames processed:\s*(\d+)", output)

        if result.returncode != 0 or not probability_match:
            safe_output = output.replace(api_key, "[REDACTED]")[-4000:]
            logger.error("NVIDIA detector failed (exit=%s). Output tail:\n%s", result.returncode, safe_output)
            if "RESOURCE_EXHAUSTED" in output or "exceeded rate limit" in output.lower():
                logger.warning("NVIDIA rate limit reached; request was not automatically retried.")
                raise HTTPException(
                    status_code=429,
                    detail="NVIDIA's free detector is currently rate-limiting requests because its shared capacity is busy. Please wait 5–10 minutes before trying again. Repeated attempts will not make it faster.",
                )
            elif "UNAUTHENTICATED" in output or "PERMISSION_DENIED" in output:
                message = "NVIDIA rejected the API credentials or this account does not have access to the detector."
            elif "UNAVAILABLE" in output or "DEADLINE_EXCEEDED" in output:
                message = "NVIDIA's analysis service is unavailable or timed out. Please try again later."
            elif "INVALID_ARGUMENT" in output and "format not supported" in output.lower():
                message = "NVIDIA could not decode this converted video. Please try a different video file."
            elif "No module named" in output or "ModuleNotFoundError" in output:
                message = "The NVIDIA client is missing a required Python package. The server log has the exact package error."
            elif "Configuration error" in output or "unrecognized arguments" in output:
                message = "The NVIDIA client configuration or command-line options are incorrect. The server log has the exact error."
            else:
                message = "NVIDIA analysis failed. The server log contains the detailed error."
            raise HTTPException(status_code=502, detail=message)

        probability = max(0.0, min(1.0, float(probability_match.group(1))))
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
        for path in (input_path, normalized_path):
            if path and path.exists():
                path.unlink(missing_ok=True)
        await video.close()
        ANALYSIS_LOCK.release()
