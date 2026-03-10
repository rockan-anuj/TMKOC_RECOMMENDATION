import os
import json
import random
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

app = FastAPI()

# Global variable to cache the JSON in memory across requests
OFFICIAL_DATA = []


def load_data():
    global OFFICIAL_DATA
    if not OFFICIAL_DATA:
        try:
            # Assuming merged.json is in your root directory
            with open("official_episodes.json", "r", encoding="utf-8") as f:
                OFFICIAL_DATA = json.load(f)
        except Exception as e:
            print(f"Error loading JSON: {e}")
            OFFICIAL_DATA = []


@app.get("/recommend")
@app.post("/recommend")
async def get_recommendations():
    load_data()
    if not OFFICIAL_DATA:
        return {"error": "No data found", "recommendations": []}

    weighted_pool = []

    for ep in OFFICIAL_DATA:
        try:
            num_int = int(ep.get("number", 0))
        except:
            num_int = 0

        # --- THE ERA PENALTY LOGIC ---
        # We assign a 'weight' (frequency of appearance in the pool)
        # Higher weight = Higher chance of being picked
        if num_int > 3100:
            weight = 1  # 40% reduction in chance compared to mid-era
        elif num_int > 2100:
            weight = 3  # Slight penalty
        else:
            weight = 5  # "Golden Era" - Highest priority

        # Add the episode reference to the pool multiple times based on weight
        # This is a very fast way to do weighted random sampling in pure Python
        weighted_pool.extend([ep] * weight)

    # Pick 40 unique recommendations from the weighted pool
    # Using a set to ensure we don't pick the same episode multiple times
    final_selection = []
    attempts = 0
    while len(final_selection) < 40 and attempts < 200:
        ep = random.choice(weighted_pool)
        if ep not in final_selection:
            # Add the "Reason" for your Android UI
            num = int(ep.get("number", 0))
            ep_copy = ep.copy()
            ep_copy["reason"] = "Golden Era Classic" if num <= 2100 else "Requested Era"
            final_selection.append(ep_copy)
        attempts += 1

    return {"recommendations": final_selection}


@app.get("/token", response_class=PlainTextResponse)
def get_token():
    return "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3MzgxNzQ5MTgsImV4cCI6MTczOTQ3MDkxOCwiYXVkIjoiKi5zb255bGl2LmNvbSIsImlzcyI6IlNvbnlMSVYiLCJzdWIiOiJzb21lQHNldGluZGlhLmNvbSJ9.EIcx703SmNblaBfQZ69-BtoYDfNl36_SeR9P2Pj-Oey5lZYN22e0tFgeixWYrvk7GhGnrXQDqkRbMaVZUs2AvnMcXqNHxNmawjLyhLO2cJR5ldlJ53d1JjETol8YgSGlTuqM6v_Aw0GPf5hGVvOII-GrAbpYn0d-5Ik9YdQYApp8QpAnqziPNW6aM8ilIJp2cMbc_x2rLviFMMV-6-a3YFL7NaB4nnjIiyMNb2XtLDjLeN9jP3DNI4O4FOtKddeHL6A2jh-qSRYJO3hdpkdYKr8vDZhc5nqMzLlXZskVENYD1K8ogVzZWvXM_nqHZ3weV_nS4GM6RspG4dHwKNSM1Z_IRMA3cCYvBN8rmGA8gwP6b9NpmMZE_tEsMRC5rqo1yWSzpQkyXWI8nA9zNEaAHVt2nEDp96xOTUEgLN4ZaRRvZLSDGkH6FBPBzJgy-lD1KgM9QkhHFkPmtTSrutn0CtqqULMvzsmgD-RoUBCNqizwNGpkl62Le37V9brbMPqryK4nUJah7eC5yZtjr3xJBtFIut18A7aUfCjF79p3a-QuR9cMqKGQHRc4LsVO0_V0ntXTqH1gcmzqtvNDs-WM6Xf5mfwbukOhA-cy-m4x7ajEgF1ZYmQ64AhWtBhaoybKBJ7BfAj29xdJ9eQUUJbGypfqfBdQcL5Kl1TgNTSmtGw"

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)