import json
import pickle
import re
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


def train_model():
    print("Loading Multilingual AI Model...")
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

    with open('official_episodes.json', 'r', encoding='utf-8') as f:
        official_episodes = json.load(f)
    with open('yt_history.json', 'r', encoding='utf-8') as f:
        history = json.load(f)

    print("Embedding official episodes using Name + Description...")
    official_data = {}
    official_texts = []
    official_numbers = []

    for ep in official_episodes:
        # We combine the name and the full official description to create the perfect context vector
        text = f"{ep.get('name', '')} {ep.get('description', '')}"
        official_texts.append(text)
        official_numbers.append(str(ep['number']))
        official_data[str(ep['number'])] = ep

    official_embeddings = model.encode(official_texts)

    for idx, num in enumerate(official_numbers):
        official_data[num]['embedding'] = official_embeddings[idx]

    print("Analyzing your watch history...")
    keywords = ['sony liv', 'sony pal', 'sony sab', 'taarak mehta', 'tmkoc']
    filtered_history = [
        item for item in history
        if any(
            k in item.get('title', '').lower() or k in item.get('subtitles', [{'name': ''}])[0].get('name', '').lower()
            for k in keywords)
    ]

    watch_counts = {num: 0 for num in official_numbers}
    user_preference_vectors = []
    last_watched_ep = None

    for item in filtered_history:
        title = item['title'].replace('Watched ', '')

        match = re.search(r'ep(?:isode)?\.?\s*(\d+)', title, re.IGNORECASE)

        if match and match.group(1) in official_data:
            matched_ep_num = match.group(1)
            best_match_idx = official_numbers.index(matched_ep_num)
            # SUCCESS: It found the ID in the title!
            # It now grabs the OFFICIAL description embedding (best_match_idx) instead of the YouTube title
        else:
            yt_emb = model.encode([title])[0]
            similarities = cosine_similarity([yt_emb], official_embeddings)[0]
            best_match_idx = np.argmax(similarities)
            matched_ep_num = official_numbers[best_match_idx]

        watch_counts[matched_ep_num] += 1
        user_preference_vectors.append(official_embeddings[best_match_idx])
        last_watched_ep = matched_ep_num

    if user_preference_vectors:
        taste_profile = np.mean(user_preference_vectors, axis=0)
    else:
        taste_profile = np.zeros(official_embeddings.shape[1])

    print("Saving trained profile...")
    export_data = {
        "official_data": official_data,
        "taste_profile": taste_profile,
        "watch_counts": watch_counts,
        "last_watched_ep": last_watched_ep
    }

    with open('trained_brain.pkl', 'wb') as f:
        pickle.dump(export_data, f)

    print("Training complete!")


if __name__ == "__main__":
    train_model()