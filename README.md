# REAL OR AI

Standalone public website starter for checking videos for signs of AI generation or manipulation.

## Included
- Responsive landing page with video upload and social-video URL input.
- Three-check-per-day **demo counter** stored in the visitor's browser.
- Cloudflare Worker API scaffold.

## Important current limitations
This is a frontend starter, not a working detector yet. The API deliberately returns `DETECTOR_NOT_CONFIGURED`; it does not invent an AI/human result. The three-per-day browser counter is not enforceable and can be reset or bypassed. Before public launch, add a durable server-side quota store and connect a tested provider that supports video analysis.

Social platforms may block automated access to media. Only analyse content through permitted APIs or direct URLs the user is authorised to provide. Do not scrape or bypass access controls.

## Publish frontend with GitHub Pages
1. In repository Settings → Pages.
2. Under Build and deployment choose **Deploy from a branch**.
3. Select branch `main` and folder `/(root)`, then Save.
4. Wait for the Pages deployment. GitHub documents these steps at https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site

## Backend
Deploy `worker.js` as a Cloudflare Worker and add a verified detector API integration. Store provider credentials as Worker secrets. Then set `API_BASE` in `app.js` to the Worker URL and restrict `ALLOWED_ORIGIN` to the GitHub Pages origin.

Never put secret API keys in `app.js`.
