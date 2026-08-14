import torch
import numpy as np
import pandas as pd
import json
import os
import sys

# Add backend tools directory to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../tools')))
from mrs_utils import model, X_features, df_clean, latent_embeddings


# 1. Export DeepAutoencoder Encoder to ONNX
print("Exporting model to ONNX...")
encoder = model.encoder.cpu()
encoder.eval()
dummy_input = torch.randn(1, 104)
onnx_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend/app/autoencoder_encoder.onnx'))

torch.onnx.export(
    encoder,
    dummy_input,
    onnx_path,
    export_params=True,
    opset_version=12,
    do_constant_folding=True,
    input_names=['input'],
    output_names=['output'],
    dynamic_axes={'input': {0: 'batch_size'}, 'output': {0: 'batch_size'}}
)
print(f"Model exported to {onnx_path}")

# 2. Export Latent Embeddings as a raw float32 binary file
print("Exporting latent embeddings...")
latent_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend/app/latent_embeddings.bin'))
# Ensure float32 representation
latent_embeddings_f32 = latent_embeddings.astype(np.float32)
latent_embeddings_f32.tofile(latent_path)
print(f"Latent embeddings exported to {latent_path} (size: {os.path.getsize(latent_path)} bytes)")

# 3. Export X_features as a raw float32 binary file
print("Exporting X_features...")
features_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend/app/X_features.bin'))
X_features_f32 = X_features.astype(np.float32)
X_features_f32.tofile(features_path)
print(f"X_features exported to {features_path} (size: {os.path.getsize(features_path)} bytes)")

# 4. Export tracks metadata (name, artist, spotify_id)
print("Exporting track metadata...")
metadata_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend/app/tracks_metadata.json'))

# Create a compact list of tracks: [ [name, artist, spotify_id], ... ]
tracks_list = []
for idx, row in df_clean.iterrows():
    tracks_list.append([
        str(row['name']),
        str(row['artist']),
        str(row['spotify_id'])
    ])

with open(metadata_path, 'w', encoding='utf-8') as f:
    json.dump(tracks_list, f, separators=(',', ':'))
print(f"Track metadata exported to {metadata_path} (size: {os.path.getsize(metadata_path)} bytes)")

print("All exports completed successfully!")
