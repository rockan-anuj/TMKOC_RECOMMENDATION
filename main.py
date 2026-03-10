import os
import pickle
import random
import json
from typing import Dict, List, Optional, Tuple

import numpy as np
import redis
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

app = FastAPI()

kv_url = os.getenv("REDIS_URL", "redis://localhost:6379")

# Redis client is initialized lazily to avoid slow or hanging startup
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """
    Lazily create a Redis client with short timeouts so the
    serverless function never hangs waiting on the network.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    try:
        _redis_client = redis.Redis.from_url(
            kv_url,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
            health_check_interval=30,
        )
    except redis.RedisError:
        _redis_client = None

    return _redis_client


# Heavy model / data is loaded once and reused across invocations
brain: Optional[Dict] = None
official_data: Dict = {}
_episode_numbers: List[str] = []
_episode_numbers_int: List[Optional[int]] = []
_embeddings_matrix: Optional[np.ndarray] = None


def load_brain() -> None:
    """
    Load the trained brain and precompute static structures.
    Called lazily on first use to keep cold starts minimal.
    """
    global brain, official_data, _episode_numbers, _episode_numbers_int, _embeddings_matrix
    if brain is not None:
        return

    with open("trained_brain.pkl", "rb") as f:
        brain_loaded = pickle.load(f)

    brain = brain_loaded
    official = brain_loaded["official_data"]
    official_data.update(official)

    # Precompute episode numbers, their integer forms, and embedding matrix (read‑only across requests)
    _episode_numbers = list(official_data.keys())
    _episode_numbers_int = [int(n) if n.isdigit() else None for n in _episode_numbers]
    _embeddings_matrix = np.array(
        [official_data[num]["embedding"] for num in _episode_numbers], dtype=float
    )


def _compute_cosine_similarities(taste_profile: np.ndarray) -> np.ndarray:
    """
    Lightweight cosine similarity implementation using NumPy only.
    This avoids pulling in heavy ML dependencies at runtime while
    keeping the recommendation logic equivalent.
    """
    load_brain()
    if _embeddings_matrix is None:
        return np.zeros(0, dtype=float)

    # Ensure 1D float array
    tp = np.asarray(taste_profile, dtype=float).ravel()
    emb = _embeddings_matrix

    # Handle degenerate cases defensively
    tp_norm = np.linalg.norm(tp)
    if tp_norm == 0.0:
        return np.zeros(emb.shape[0], dtype=float)

    emb_norms = np.linalg.norm(emb, axis=1)
    # Avoid division by zero; zero‑norm embeddings contribute zero similarity
    safe_norms = emb_norms.copy()
    safe_norms[safe_norms == 0.0] = 1.0

    dots = emb @ tp
    sims = dots / (tp_norm * safe_norms)
    # Any embeddings that were actually zero‑norm should be forced to 0 similarity
    sims[emb_norms == 0.0] = 0.0
    return sims


class UpdateRequest(BaseModel):
    episode_number: str


def _fallback_state_from_brain() -> Tuple[np.ndarray, Dict[str, int], Optional[str]]:
    load_brain()
    assert brain is not None  # for type‑checkers
    taste_profile = brain["taste_profile"]
    watch_counts = brain["watch_counts"]
    last_watched = brain["last_watched_ep"]
    return taste_profile, watch_counts, last_watched


def get_dynamic_state() -> Tuple[np.ndarray, Dict[str, int], Optional[str]]:
    """
    Get the latest dynamic state from Redis.
    Falls back to the bundled brain data instantly if Redis is slow or unavailable.
    """
    client = get_redis_client()
    if client is None:
        return _fallback_state_from_brain()

    try:
        taste_data = client.get("taste_profile")
    except redis.RedisError:
        return _fallback_state_from_brain()

    if taste_data:
        try:
            taste_profile = np.array(json.loads(taste_data), dtype=float)
            watch_counts_raw = client.get("watch_counts")
            watch_counts: Dict[str, int] = (
                json.loads(watch_counts_raw) if watch_counts_raw else {}
            )
            last_watched_raw = client.get("last_watched_ep")
            last_watched = (
                last_watched_raw.decode("utf-8") if last_watched_raw else None
            )
            return taste_profile, watch_counts, last_watched
        except (ValueError, TypeError, redis.RedisError):
            # Corrupt or unexpected data, fall back to safe defaults
            return _fallback_state_from_brain()

    # First time running or empty KV: seed from bundled brain
    taste_profile, watch_counts, last_watched = _fallback_state_from_brain()

    try:
        client.set("taste_profile", json.dumps(taste_profile.tolist()))
        client.set("watch_counts", json.dumps(watch_counts))
        if last_watched:
            client.set("last_watched_ep", last_watched)
    except redis.RedisError:
        # If caching fails, we still return a valid in‑memory state
        pass

    return taste_profile, watch_counts, last_watched


@app.post("/recommend")
async def get_recommendations():
    # Always fetch the freshest memory from the cloud (or safe fallback)
    taste_profile, watch_counts, last_watched_ep = get_dynamic_state()

    # Ensure brain and static embeddings are initialized
    load_brain()
    ep_numbers_local = _episode_numbers
    ep_numbers_int_local = _episode_numbers_int

    similarities = _compute_cosine_similarities(taste_profile)

    scores = {}
    unwatched_pool = []

    for idx, num in enumerate(ep_numbers_local):
        num_int = ep_numbers_int_local[idx]
        score = similarities[idx]

        # The Era Penalty
        if num_int is not None and num_int > 3100:
            score -= 0.4
        if num_int is not None and num_int > 2100:
            score -= 0.1

        # Sequential Boost
        if last_watched_ep and last_watched_ep.isdigit() and num_int is not None:
            if num_int == int(last_watched_ep) + 1:
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

    results: List[Dict] = []
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
async def update_history(data: UpdateRequest):
    # Fetch current state from the cloud (or safe fallback)
    taste_profile, watch_counts, last_watched_ep = get_dynamic_state()

    ep_num = str(data.episode_number)
    if ep_num not in official_data:
        return {"error": "Episode not found"}

    # Update logic
    watch_counts[ep_num] = watch_counts.get(ep_num, 0) + 1
    # Ensure brain and static data are initialized
    load_brain()
    ep_embedding = official_data[ep_num]["embedding"]
    taste_profile = (taste_profile * 0.9) + (ep_embedding * 0.1)

    # Push the new state back to Redis / KV without blocking the request on failures
    client = get_redis_client()
    if client is not None:
        try:
            client.set("taste_profile", json.dumps(taste_profile.tolist()))
            client.set("watch_counts", json.dumps(watch_counts))
            client.set("last_watched_ep", ep_num)
        except redis.RedisError:
            # Ignore persistence failures to avoid user‑visible errors
            pass

    return {"status": "success", "message": "Memory updated in the cloud."}

@app.get("/token", response_class=PlainTextResponse)
def get_token():
    return PlainTextResponse("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3MzgxNzQ5MTgsImV4cCI6MTczOTQ3MDkxOCwiYXVkIjoiKi5zb255bGl2LmNvbSIsImlzcyI6IlNvbnlMSVYiLCJzdWIiOiJzb21lQHNldGluZGlhLmNvbSJ9.EIcx703SmNblaBfQZ69-BtoYDfNl36_SeR9P2Pj-Oey5lZYN22e0tFgeixWYrvk7GhGnrXQDqkRbMaVZUs2AvnMcXqNHxNmawjLyhLO2cJR5ldlJ53d1JjETol8YgSGlTuqM6v_Aw0GPf5hGVvOII-GrAbpYn0d-5Ik9YdQYApp8QpAnqziPNW6aM8ilIJp2cMbc_x2rLviFMMV-6-a3YFL7NaB4nnjIiyMNb2XtLDjLeN9jP3DNI4O4FOtKddeHL6A2jh-qSRYJO3hdpkdYKr8vDZhc5nqMzLlXZskVENYD1K8ogVzZWvXM_nqHZ3weV_nS4GM6RspG4dHwKNSM1Z_IRMA3cCYvBN8rmGA8gwP6b9NpmMZE_tEsMRC5rqo1yWSzpQkyXWI8nA9zNEaAHVt2nEDp96xOTUEgLN4ZaRRvZLSDGkH6FBPBzJgy-lD1KgM9QkhHFkPmtTSrutn0CtqqULMvzsmgD-RoUBCNqizwNGpkl62Le37V9brbMPqryK4nUJah7eC5yZtjr3xJBtFIut18A7aUfCjF79p3a-QuR9cMqKGQHRc4LsVO0_V0ntXTqH1gcmzqtvNDs-WM6Xf5mfwbukOhA-cy-m4x7ajEgF1ZYmQ64AhWtBhaoybKBJ7BfAj29xdJ9eQUUJbGypfqfBdQcL5Kl1TgNTSmtGw")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)