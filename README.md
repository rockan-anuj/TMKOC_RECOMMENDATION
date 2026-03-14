# TMKOC Recommendation

## Why `/token` and `/recommend` don't work on Streamlit

**Streamlit Cloud only runs Streamlit.** It does not run FastAPI, so URLs like:

- `https://yoursite.streamlit.app/token`
- `https://yoursite.streamlit.app/recommend`

will not work. Streamlit serves only the Streamlit UI, not your API routes.

## One app with UI + API: deploy FastAPI (e.g. Render)

To have **both** a simple UI **and** the backend (`/token`, `/recommend`) at one URL:

1. Deploy this repo as a **Web Service** on **Render** (or Railway, Fly.io).
2. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Your app URL will then have:
   - **`/`** — simple web UI (recommendations button + API links)
   - **`/token`** — token (e.g. for Android)
   - **`/recommend`** — GET or POST for JSON recommendations
   - **`/health`** — health check

Use this **Render URL** in your Android app (e.g. `https://your-app.onrender.com/token`).

## Streamlit Cloud (UI only)

Set Main file path to **`app.py`**. For the API, host **main.py** on Render as above and use that base URL for `/token` and `/recommend`.
