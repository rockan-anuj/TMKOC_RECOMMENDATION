# app.py
import json
import re
from datetime import datetime
from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

app = FastAPI()

# 1. Load the smart NLP model (MiniLM is fast and highly accurate for semantic text matching)
model = SentenceTransformer('all-MiniLM-L6-v2')

# 2. Global variables to hold our data and embeddings
official_episodes = []
official_embeddings = None
user_history_profile = {}  # Maps hour of the day (0-23) to preferred episode vectors


def load_and_train_data():
    global official_episodes, official_embeddings, user_history_profile

    # Load your official episodes JSON (assuming it's saved locally)
    with open('official_episodes.json', 'r', encoding='utf-8') as f:
        official_episodes = json.load(f)

    # Create rich text representations for official episodes (Title + Description)
    official_texts = [f"{ep['name']} {ep.get('description', '')}" for ep in official_episodes]
    official_embeddings = model.encode(official_texts)

    # Load your YouTube History JSON
    with open('yt_history.json', 'r', encoding='utf-8') as f:
        history = json.load(f)

    # Filter history for Sony/Taarak Mehta related content
    keywords = ['sony liv', 'sony pal', 'sony sab', 'taarak mehta', 'tmkoc']
    filtered_history = []
    for item in history:
        title = item.get('title', '').lower()
        subtitles = item.get('subtitles', [{'name': ''}])[0]['name'].lower()
        if any(k in title or k in subtitles for k in keywords):
            filtered_history.append(item)

    # Build a time-based profile
    # Group watched video embeddings by the hour of the day they were watched
    hourly_vectors = {i: [] for i in range(24)}

    # Process history titles to embeddings
    history_titles = [item['title'].replace('Watched ', '') for item in filtered_history]
    if history_titles:
        history_embeddings = model.encode(history_titles)

        for idx, item in enumerate(filtered_history):
            # Parse the time (e.g., "2023-03-19T14:43:45.652Z")
            watch_time = datetime.strptime(item['time'][:19], "%Y-%m-%dT%H:%M:%S")
            hour = watch_time.hour
            hourly_vectors[hour].append(history_embeddings[idx])

    # Calculate the average viewing preference (centroid vector) for each hour
    for hour in range(24):
        if hourly_vectors[hour]:
            user_history_profile[hour] = np.mean(hourly_vectors[hour], axis=0)
        else:
            # If no data for this hour, fallback to the global average of all watched videos
            if history_titles:
                user_history_profile[hour] = np.mean(history_embeddings, axis=0)


# Run training on startup
load_and_train_data()


class RequestData(BaseModel):
    current_time: str  # ISO format string from Cloudflare


@app.post("/recommend")
def get_recommendations(data: RequestData):
    # Parse the incoming time from Cloudflare worker
    request_dt = datetime.fromisoformat(data.current_time.replace('Z', '+00:00'))
    current_hour = request_dt.hour

    # Get the user's viewing preference for this specific hour
    preferred_vector = user_history_profile.get(current_hour)

    if preferred_vector is None:
        return {"error": "Insufficient history data to generate recommendations."}

    # Calculate cosine similarity between the preferred vector for this time and ALL official episodes
    similarities = cosine_similarity([preferred_vector], official_embeddings)[0]

    # Get the top 10 matches (indices of the highest similarity scores)
    top_10_indices = np.argsort(similarities)[::-1][:10]

    # Format the response
    recommendations = []
    for idx in top_10_indices:
        ep = official_episodes[idx]
        recommendations.append({
            "episode_number": ep["number"],
            "title": ep["name"],
            "description": ep["description"],
            "thumbnail": ep["thumbnail"],
            "confidence_score": round(float(similarities[idx]) * 100, 2)
        })

    return {"recommendations": recommendations}


if __name__ == "__main__":
    import uvicorn

    # Run the API on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)