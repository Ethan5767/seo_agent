# SEO Scan — web UI (Next.js)

The front end for the URL-audit MVP. It is **just the face**: it POSTs to
`/api/scan`, a server-side route that proxies to the Python backend
(`wf-scan-web`). All the real work is in the Python engine.

## Run it (two terminals, on your Mac)

**Terminal 1 — the Python backend (the engine):**
```bash
cd ~/seo_agent
export CRUX_API_KEY=<your key>          # optional: real Core Web Vitals
export ANTHROPIC_API_KEY=<your key>     # optional: Model B real fix (needs claude CLI)
.venv/bin/wf-scan-web                    # serves http://127.0.0.1:8765
```

**Terminal 2 — the Next.js UI:**
```bash
cd ~/seo_agent/web
npm install        # first time only (needs internet)
npm run dev        # serves http://localhost:3000
```

Open http://localhost:3000, paste a URL (+ a repo path to fix), pick Model A/B, Run.

## Config
- `PYTHON_API` (default `http://127.0.0.1:8765`) — where the Next server finds the backend.
