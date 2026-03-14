import os
import sys
import json
import random
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, HTMLResponse

app = FastAPI()

# Global variable to cache the JSON in memory across requests
OFFICIAL_DATA = []


def _index_html() -> str:
    """Simple UI + API links. Same origin so /token and /recommend work when hosted as FastAPI."""
    return """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TMKOC Recommendations</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 600px; margin: 2rem auto; padding: 0 1rem; }
    h1 { color: #333; }
    button { padding: 0.5rem 1rem; font-size: 1rem; cursor: pointer; }
    #out { margin-top: 1rem; }
    .ep { margin: 0.4rem 0; padding: 0.4rem; background: #f5f5f5; border-radius: 6px; }
    .links { margin-top: 1.5rem; font-size: 0.9rem; color: #666; }
    .links a { color: #1a73e8; }
  </style>
</head>
<body>
  <h1>Taarak Mehta Ka Oolta Chashmah</h1>
  <p>Episode recommendations</p>
  <button id="btn">Get recommendations</button>
  <div id="out"></div>
  <div class="links">
    <p><strong>API (same host):</strong></p>
    <p><a href="/recommend" target="_blank">GET /recommend</a> — JSON recommendations</p>
    <p><a href="/token" target="_blank">GET /token</a> — token (e.g. for Android)</p>
    <p><a href="/health" target="_blank">GET /health</a> — health check</p>
  </div>
  <script>
    document.getElementById('btn').onclick = async () => {
      const out = document.getElementById('out');
      out.innerHTML = 'Loading...';
      try {
        const r = await fetch('/recommend');
        const j = await r.json();
        const list = j.recommendations || [];
        out.innerHTML = list.length ? list.slice(0, 15).map(ep =>
          '<div class="ep"><b>' + (ep.number || '') + '</b> — ' + (ep.name || '') + ' <small>(' + (ep.reason || '') + ')</small></div>'
        ).join('') + (list.length > 15 ? '<p>... and ' + (list.length - 15) + ' more.</p>' : '') : '<p>No data.</p>';
      } catch (e) {
        out.innerHTML = '<p style="color:red">Error: ' + e.message + '</p>';
      }
    };
  </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    """Serve minimal UI. /token and /recommend work on this same host when you deploy FastAPI (e.g. Render)."""
    return _index_html()


@app.get("/health")
def health():
    """Health check for platforms."""
    return {"status": "ok"}


def load_data():
    global OFFICIAL_DATA
    if not OFFICIAL_DATA:
        try:
            with open("official_episodes.json", "r", encoding="utf-8") as f:
                OFFICIAL_DATA = json.load(f)
        except Exception as e:
            print(f"Error loading JSON: {e}")
            OFFICIAL_DATA = []


def _compute_recommendations():
    """Shared logic: returns list of episode dicts with 'reason'. Used by API and Streamlit UI."""
    load_data()
    if not OFFICIAL_DATA:
        return []
    weighted_pool = []
    for ep in OFFICIAL_DATA:
        try:
            num_int = int(ep.get("number", 0))
        except Exception:
            num_int = 0
        if num_int > 3100:
            weight = 1
        elif num_int > 2100:
            weight = 3
        else:
            weight = 5
        weighted_pool.extend([ep] * weight)
    final_selection = []
    attempts = 0
    while len(final_selection) < 40 and attempts < 200:
        ep = random.choice(weighted_pool)
        if ep not in final_selection:
            num = int(ep.get("number", 0))
            ep_copy = ep.copy()
            ep_copy["reason"] = "Golden Era Classic" if num <= 2100 else "Requested Era"
            final_selection.append(ep_copy)
        attempts += 1
    return final_selection


@app.get("/recommend")
@app.post("/recommend")
async def get_recommendations():
    recs = _compute_recommendations()
    if not recs:
        return {"error": "No data found", "recommendations": []}
    return {"recommendations": recs}


@app.get("/token", response_class=PlainTextResponse)
def get_token():
    return PlainTextResponse("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3MzgxNzQ5MTgsImV4cCI6MTczOTQ3MDkxOCwiYXVkIjoiKi5zb255bGl2LmNvbSIsImlzcyI6IlNvbnlMSVYiLCJzdWIiOiJzb21lQHNldGluZGlhLmNvbSJ9.EIcx703SmNblaBfQZ69-BtoYDfNl36_SeR9P2Pj-Oey5lZYN22e0tFgeixWYrvk7GhGnrXQDqkRbMaVZUs2AvnMcXqNHxNmawjLyhLO2cJR5ldlJ53d1JjETol8YgSGlTuqM6v_Aw0GPf5hGVvOII-GrAbpYn0d-5Ik9YdQYApp8QpAnqziPNW6aM8ilIJp2cMbc_x2rLviFMMV-6-a3YFL7NaB4nnjIiyMNb2XtLDjLeN9jP3DNI4O4FOtKddeHL6A2jh-qSRYJO3hdpkdYKr8vDZhc5nqMzLlXZskVENYD1K8ogVzZWvXM_nqHZ3weV_nS4GM6RspG4dHwKNSM1Z_IRMA3cCYvBN8rmGA8gwP6b9NpmMZE_tEsMRC5rqo1yWSzpQkyXWI8nA9zNEaAHVt2nEDp96xOTUEgLN4ZaRRvZLSDGkH6FBPBzJgy-lD1KgM9QkhHFkPmtTSrutn0CtqqULMvzsmgD-RoUBCNqizwNGpkl62Le37V9brbMPqryK4nUJah7eC5yZtjr3xJBtFIut18A7aUfCjF79p3a-QuR9cMqKGQHRc4LsVO0_V0ntXTqH1gcmzqtvNDs-WM6Xf5mfwbukOhA-cy-m4x7ajEgF1ZYmQ64AhWtBhaoybKBJ7BfAj29xdJ9eQUUJbGypfqfBdQcL5Kl1TgNTSmtGw")

# When run by Streamlit Cloud ("streamlit run main.py"), show UI and do NOT start uvicorn (avoids port 8000 conflict).
if "streamlit" in sys.modules:
    import streamlit as st

    st.set_page_config(page_title="TMKOC Recommendations", layout="centered")
    st.title("Taarak Mehta Ka Oolta Chashmah")
    st.caption("Episode recommendations")
    if st.button("Get recommendations"):
        recs = _compute_recommendations()
        if recs:
            for ep in recs[:15]:
                st.markdown(f"**{ep.get('number', '')}** — {ep.get('name', '')} ({ep.get('reason', '')})")
            if len(recs) > 15:
                st.info(f"... and {len(recs) - 15} more.")
        else:
            st.warning("No data loaded.")
    st.divider()
    st.markdown("Use **GET/POST** `/recommend` on this app for JSON API (e.g. from Android).")

# Do NOT start uvicorn from this file. Streamlit Cloud runs "streamlit run main.py" and
# would hit "address already in use" if we started uvicorn here. To run the API locally:
#   uvicorn main:app --host 0.0.0.0 --port 8000