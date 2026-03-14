"""
Streamlit app for TMKOC Recommendations.
Run with: streamlit run app.py
Health check: use path /_stcore/health in your deployment platform.
"""
import json
import random

import streamlit as st

st.set_page_config(page_title="TMKOC Recommendations", layout="centered")

# Cache data in memory
@st.cache_data
def load_data():
    try:
        with open("official_episodes.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return []


def get_recommendations():
    data = load_data()
    if not data:
        return []

    weighted_pool = []
    for ep in data:
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


st.title("Taarak Mehta Ka Oolta Chashmah")
st.caption("Episode recommendations")

if st.button("Get recommendations"):
    recs = get_recommendations()
    if recs:
        for ep in recs[:10]:
            st.markdown(f"**{ep.get('number', '')}** — {ep.get('name', '')} ({ep.get('reason', '')})")
        if len(recs) > 10:
            st.info(f"... and {len(recs) - 10} more. Use the API for full list.")
    else:
        st.warning("No data loaded.")

st.divider()
st.markdown("API: `POST /recommend` on this server (FastAPI) for JSON recommendations.")
