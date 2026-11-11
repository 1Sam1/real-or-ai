# REAL OR AI Python API

This service accepts MP4 uploads and invokes NVIDIA's official Synthetic Video Detector v1 Python gRPC client against NVIDIA's hosted NVCF endpoint.

## Deploy on Render

Use the repository Blueprint (`render.yaml`) or create a Python web service with:
- Root directory: `backend`
- Build command: `pip install -r requirements.txt && git clone --depth 1 https://github.com/NVIDIA-Maxine/nim-clients.git /opt/nim-clients`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Secret environment variable: `NVIDIA_API_KEY`
- Environment variable: `ALLOWED_ORIGIN=https://1sam1.github.io`

The NVIDIA API key must be added to Render as a secret too. A secret stored in a Cloudflare Worker is not automatically available to Render.

## Current prototype limits

- Upload only; direct social-media URL fetching is not enabled.
- MP4 container required; NVIDIA documents H.264 video and does not support variable-frame-rate video.
- Application upload cap is 50 MB for this first hosted test.
- The NVIDIA detector's documented conservative default classification threshold is 0.30. The UI must describe results as probabilistic, not proof.
- The three-per-day counter in the static website is browser-side demo logic, not secure enforcement. Do not announce a public production launch until durable server-side quotas, abuse controls, and privacy/retention controls are implemented.

The NVIDIA client is downloaded from https://github.com/NVIDIA-Maxine/nim-clients and is distributed under the MIT license in its own repository. Refer to its license and documentation for usage terms.
