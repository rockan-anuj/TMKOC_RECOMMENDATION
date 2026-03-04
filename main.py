import os
import pickle
import random
import json
import numpy as np
import redis
from fastapi import FastAPI
from pydantic import BaseModel
from sklearn.metrics.pairwise import cosine_similarity

app = FastAPI()

kv_url = os.getenv("KV_URL", "redis://localhost:6379")
redis_client = redis.Redis.from_url(kv_url)

with open('trained_brain.pkl', 'rb') as f:
    brain = pickle.load(f)

official_data = brain["official_data"]


class UpdateRequest(BaseModel):
    episode_number: str


# Helper function to get the latest dynamic state from Redis
def get_dynamic_state():
    taste_data = redis_client.get("taste_profile")

    if taste_data:
        # Load from Redis
        taste_profile = np.array(json.loads(taste_data))
        watch_counts = json.loads(redis_client.get("watch_counts"))
        last_watched = redis_client.get("last_watched_ep")
        if last_watched:
            last_watched = last_watched.decode('utf-8')
    else:
        # First time running! Seed Redis with the original data from train.py
        taste_profile = brain["taste_profile"]
        watch_counts = brain["watch_counts"]
        last_watched = brain["last_watched_ep"]

        # Save to Redis for next time
        redis_client.set("taste_profile", json.dumps(taste_profile.tolist()))
        redis_client.set("watch_counts", json.dumps(watch_counts))
        if last_watched:
            redis_client.set("last_watched_ep", last_watched)

    return taste_profile, watch_counts, last_watched


@app.get("/recommend")
def get_recommendations():
    # Always fetch the freshest memory from the cloud
    taste_profile, watch_counts, last_watched_ep = get_dynamic_state()

    ep_numbers = list(official_data.keys())
    embeddings = [official_data[num]['embedding'] for num in ep_numbers]

    similarities = cosine_similarity([taste_profile], embeddings)[0]

    scores = {}
    unwatched_pool = []

    for idx, num in enumerate(ep_numbers):
        score = similarities[idx]

        # The Era Penalty
        if num.isdigit() and int(num) > 3100:
            score -= 0.4
        if num.isdigit() and int(num) > 2100:
            score -= 0.1

        # Sequential Boost
        if last_watched_ep and num.isdigit() and last_watched_ep.isdigit():
            if int(num) == int(last_watched_ep) + 1:
                score += 0.8

        # View Penalty
        views = watch_counts.get(num, 0)
        if views > 0:
            score -= (views * 0.3)
        else:
            unwatched_pool.append(num)

        scores[num] = score

    # ADVANCED JITTER
    noisy_scores = {}
    for num, base_score in scores.items():
        jitter = random.uniform(0.0, 0.25)
        noisy_scores[num] = base_score + jitter

    sorted_eps = sorted(noisy_scores.keys(), key=lambda k: noisy_scores[k], reverse=True)

    # 40-Episode Mix
    top_smart_recommendations = sorted_eps[:35]

    sour_mix = []
    if unwatched_pool:
        safe_unwatched = [ep for ep in unwatched_pool if ep not in top_smart_recommendations]
        safe_unwatched_classic = [ep for ep in safe_unwatched if ep.isdigit() and int(ep) <= 3000]

        if safe_unwatched_classic:
            sour_mix = random.sample(safe_unwatched_classic, min(5, len(safe_unwatched_classic)))

    final_playlist_numbers = top_smart_recommendations + sour_mix
    random.shuffle(final_playlist_numbers)

    results = []
    for num in final_playlist_numbers:
        ep = official_data[num]

        reason = "Next in sequence" if (last_watched_ep and str(num) == str(int(last_watched_ep) + 1)) else \
            "Something totally new" if num in sour_mix else \
                "Because you might like it"

        results.append({
            "name": ep.get("name", ""),
            "number": ep.get("number", ""),
            "id": ep.get("id", ""),
            "thumbnail": ep.get("thumbnail", ""),
            "description": ep.get("description", ""),
            "sprite": ep.get("sprite", ""),
            "duration": ep.get("duration", ""),
            "date": ep.get("date", ""),
            "reason": reason
        })

    return {"recommendations": results}


@app.post("/update")
def update_history(data: UpdateRequest):
    # Fetch current state from the cloud
    taste_profile, watch_counts, last_watched_ep = get_dynamic_state()

    ep_num = str(data.episode_number)
    if ep_num not in official_data:
        return {"error": "Episode not found"}

    # Update logic
    watch_counts[ep_num] = watch_counts.get(ep_num, 0) + 1
    ep_embedding = official_data[ep_num]['embedding']
    taste_profile = (taste_profile * 0.9) + (ep_embedding * 0.1)

    # Push the new state back to Vercel KV
    redis_client.set("taste_profile", json.dumps(taste_profile.tolist()))
    redis_client.set("watch_counts", json.dumps(watch_counts))
    redis_client.set("last_watched_ep", ep_num)

    return {"status": "success", "message": "Memory updated in the cloud."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)