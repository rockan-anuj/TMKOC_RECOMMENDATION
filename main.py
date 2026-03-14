import os
import sys
import json
import random
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

app = FastAPI()

# Global variable to cache the JSON in memory across requests
OFFICIAL_DATA = []


@app.get("/")
@app.get("/health")
def health():
    """Used by platforms (Render, Netlify, etc.) for health checks. Must return 200."""
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