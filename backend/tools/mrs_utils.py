import numpy as np
import pandas as pd 
from sklearn.preprocessing import MinMaxScaler 
from sklearn.feature_extraction.text import TfidfVectorizer 
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import train_test_split
from sklearn.metrics.pairwise import cosine_similarity
import os

# Define relative path locations dynamically
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.abspath(os.path.join(CURRENT_DIR, '../data/music_recommendation_system/msd_music_info.csv'))
MODEL_PATH = os.path.abspath(os.path.join(CURRENT_DIR, '../models/music_recommendation_system.pth'))

# Load dataset
df = pd.read_csv(DATASET_PATH)
df_clean = df.dropna(subset=['tags'])

# normalize continuous numerical audio features, so excluding key which is numeric
numerical_cols = ['danceability', 'energy', 'loudness', 'speechiness', 'acousticness', 'instrumentalness', 'liveness', 'valence', 'tempo']
scaler = MinMaxScaler() # scales data to fit between 0 and 1
scaled_numerical = scaler.fit_transform(df_clean[numerical_cols])

cleaned_tags = df_clean['tags'].str.replace(',',' ').str.replace('_', ' ')
tfidf = TfidfVectorizer(max_features=200) 
tfidf_matrix = tfidf.fit_transform(cleaned_tags).toarray()

X_features = np.hstack((scaled_numerical, tfidf_matrix))

class AutoencoderDataset(Dataset):
    def __init__(self, features_array):
        self.features = torch.tensor(features_array, dtype=torch.float32)

    def __len__(self):
        return len(self.features)

    def __getitem__(self, idx):
        return self.features[idx], self.features[idx]
        
# split features into 85 train 15 val
X_train, X_val = train_test_split(X_features, test_size=0.15, random_state=42)

# create loaders for batching
train_loader = DataLoader(AutoencoderDataset(X_train), batch_size=64, shuffle=True) 
val_loader = DataLoader(AutoencoderDataset(X_val), batch_size=64, shuffle=False)

class DeepAutoencoder(nn.Module):
    def __init__(self, input_dim, latent_dim = 16):
        super(DeepAutoencoder, self).__init__()

        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, latent_dim)
        )

        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 128),
            nn.ReLU(),
            nn.Linear(128, input_dim),
            nn.Sigmoid()
        )
    def forward(self, x):
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        return reconstructed, latent

# determine hardware
device = torch.device('cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu')

# model instantiated
input_dimension = X_features.shape[1]
model = DeepAutoencoder(input_dim = input_dimension).to(device)

# setup mean squared loss and adam optimizer
criterion = nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

# Load model weights if they exist, otherwise train the model
if os.path.exists(MODEL_PATH):
    print(f"Loading pre-trained music recommendation model from {MODEL_PATH}")
    model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
    model.eval()
else:
    print("Pre-trained model not found. Training model from scratch...")
    NUM_EPOCHS = 15
    model.train()
    for epoch in range(NUM_EPOCHS):
        train_loss = 0.0
        for data, _ in train_loader:
            data = data.to(device)
            optimizer.zero_grad()
            outputs, _ = model(data)
            loss = criterion(outputs, data)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * data.size(0)
        train_loss /= len(train_loader.dataset)
        print(f"Epoch {epoch+1}/{NUM_EPOCHS}, Loss: {train_loss:.6f}")
    
    # Save the newly trained model
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    torch.save(model.state_dict(), MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")
    model.eval()

# Generate latent embeddings
all_features_tensor = torch.tensor(X_features, dtype=torch.float32).to(device)
with torch.no_grad():
    _, latent_embeddings = model(all_features_tensor)

# move embeddings back to cpu and convert to a numpy array for scikit learn
latent_embeddings = latent_embeddings.cpu().numpy()

# recommendation function using 2d coordinate-based emotion mapping
def recommend_song(current_title, current_artist, arousal, pleasure, excluded, top_k=10):
    if excluded is None:
        excluded = []
        
    # normalize inputs to a [0,1] range
    A = arousal / 100.0
    P = pleasure / 100.0 

    # find the current song in our cleaned dataset
    song_idx = df_clean[
        (df_clean['name'].str.lower() == current_title.lower()) &
        (df_clean['artist'].str.lower() == current_artist.lower())
    ].index
    
    if len(song_idx) == 0:
        # fall back to search by title if artist not found
        song_idx = df_clean[(df_clean['name'].str.lower() == current_title.lower())].index
        if len(song_idx) == 0:
            # If still not found, fall back to using the mean feature vector of the dataset
            # to recommend purely based on the desired arousal and pleasure levels.
            query_features = np.mean(X_features, axis=0)
            pos = -1
        else:
            idx = song_idx[0]
            pos = df_clean.index.get_loc(idx)
            query_features = X_features[pos].copy()
    else:
        idx = song_idx[0]
        pos = df_clean.index.get_loc(idx)
        query_features = X_features[pos].copy()

    # apply 2d emotion mapping on acoustic columns:
    query_features[1] = query_features[1] * (0.4 + 0.6 * A) 
    query_features[2] = query_features[2] * (0.4 + 0.6 * A)
    query_features[4] = min(query_features[4] + (1.0 - query_features[4]) * 0.5 * (1.0 - A), 0.95)
    query_features[3] = query_features[3] * (1.0 - 0.6 * A)

    # PLEASURE
    query_features[7] = min(query_features[7] + (1.0 - query_features[7]) * 0.4 * P, 0.95)

    # project query features into the latent space using the encoder
    query_tensor = torch.tensor(query_features.reshape(1,-1), dtype=torch.float32).to(device)
    with torch.no_grad():
        query_latent = model.encoder(query_tensor).cpu().numpy()
    
    # compute cosine similarity in the latent space
    similarities = cosine_similarity(query_latent, latent_embeddings)[0]

    # exploration vs exploitation control
    exploration_weight = 1.0 - P
    if exploration_weight > 0: 
        np.random.seed(42) # for reproducibility
        noise = np.random.normal(0, 0.05 * exploration_weight, size=similarities.shape)
        similarities = similarities + noise
    
    # sort similarities and get top k matches excluding song itself
    sorted_indices = np.argsort(similarities)[::-1]


    recommendations = []
    queue = []
    for rank_idx in sorted_indices:
        if rank_idx == pos:
            continue
        rec_song = df_clean.iloc[rank_idx]
        string_song = f"{rec_song['name']} - {rec_song['artist']}"
        if string_song in excluded: 
            continue # skip
        
        recommendations.append({'name': rec_song['name'], 'artist': rec_song['artist'], 'similarity': float(similarities[rank_idx])})
        queue.append(rec_song['spotify_id'])
        if len(recommendations) >= top_k:
            break
            
    return pd.DataFrame(recommendations), queue

def get_uri(title):
    result = df_clean.loc[df['name'] == title, 'spotify_id'].values[0] 
    # no dupes so no issue finding corresponding title
    return result