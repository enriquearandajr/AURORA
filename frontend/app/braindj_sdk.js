/**
 * Brain DJ Interface Client SDK
 * Runs the neuroscience deep-learning music recommendation system entirely inside the browser.
 */

// Helper to fetch assets with progress tracking
async function fetchWithProgress(url, onProgress) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    const contentLength = response.headers.get('content-length');
    if (!contentLength) {
        const buf = await response.arrayBuffer();
        if (onProgress) onProgress(100);
        return buf;
    }
    const total = parseInt(contentLength, 10);
    let loaded = 0;
    const reader = response.body.getReader();
    const chunks = [];
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        loaded += value.byteLength;
        if (onProgress) {
            onProgress(Math.round((loaded / total) * 100));
        }
    }
    const allChunks = new Uint8Array(loaded);
    let position = 0;
    for (let chunk of chunks) {
        allChunks.set(chunk, position);
        position += chunk.byteLength;
    }
    return allChunks.buffer;
}

// Box-Muller transform to generate normally distributed random noise for exploration
function randomNormal(mean, stdDev) {
    const u1 = Math.random();
    const u2 = Math.random();
    const randStdNormal = Math.sqrt(-2.0 * Math.log(u1)) * Math.sin(2.0 * Math.PI * u2);
    return mean + stdDev * randStdNormal;
}

class BrainDJEngine {
    constructor() {
        this.session = null;
        this.latentEmbeddings = null;
        this.X_features = null;
        this.metadata = null;
        this.numEmbeddings = 49556;
        this.latentDim = 16;
        this.featureDim = 104;
        this.meanFeatures = null;
    }

    /**
     * Initializes the SDK by downloading the ONNX model, latent embeddings, features, and metadata.
     * @param {Object} paths - Paths to the assets
     * @param {Function} onProgress - Callback triggered with loading progress text
     */
    async initialize(paths = {}, onProgress) {
        const modelUrl = paths.model || 'autoencoder_encoder.onnx';
        const latentUrl = paths.latent || 'latent_embeddings.bin';
        const featuresUrl = paths.features || 'X_features.bin';
        const metadataUrl = paths.metadata || 'tracks_metadata.json';

        try {
            if (onProgress) onProgress("Loading ONNX neural model...", 0);
            this.session = await ort.InferenceSession.create(modelUrl);

            if (onProgress) onProgress("Downloading latent database...", 10);
            const latentBuf = await fetchWithProgress(latentUrl, (p) => {
                if (onProgress) onProgress(`Downloading latent database... ${p}%`, 10 + Math.round(p * 0.3));
            });
            this.latentEmbeddings = new Float32Array(latentBuf);

            if (onProgress) onProgress("Downloading track catalog features...", 40);
            const featuresBuf = await fetchWithProgress(featuresUrl, (p) => {
                if (onProgress) onProgress(`Downloading catalog features... ${p}%`, 40 + Math.round(p * 0.4));
            });
            this.X_features = new Float32Array(featuresBuf);

            if (onProgress) onProgress("Loading track catalogs...", 80);
            const metadataResponse = await fetch(metadataUrl);
            this.metadata = await metadataResponse.json();

            // Pre-calculate the mean feature vector for fallback mode (when current song is not in the database)
            if (onProgress) onProgress("Optimizing database search parameters...", 95);
            this.meanFeatures = new Float32Array(this.featureDim);
            for (let j = 0; j < this.featureDim; j++) {
                let sum = 0;
                for (let i = 0; i < this.numEmbeddings; i++) {
                    sum += this.X_features[i * this.featureDim + j];
                }
                this.meanFeatures[j] = sum / this.numEmbeddings;
            }

            if (onProgress) onProgress("Ready", 100);
            console.log("Brain DJ ML Engine successfully initialized!");
        } catch (err) {
            console.error("Failed to initialize Brain DJ Engine:", err);
            throw err;
        }
    }

    /**
     * Recommends a track based on the currently playing song and cognitive states.
     * @param {string} currentTitle - Current song name
     * @param {string} currentArtist - Current artist name
     * @param {number} arousal - User arousal value (0 - 100)
     * @param {number} pleasure - User pleasure value (0 - 100)
     * @param {Array} excluded - List of track strings ("Title - Artist") to exclude
     * @param {number} topK - Number of recommendations to return
     */
    async recommendSong(currentTitle, currentArtist, arousal, pleasure, excluded = [], topK = 10) {
        if (!this.session || !this.latentEmbeddings || !this.X_features || !this.metadata) {
            throw new Error("Brain DJ Engine is not initialized.");
        }

        const A = arousal / 100.0;
        const P = pleasure / 100.0;

        // Find the index of the currently playing song in the local database
        let pos = -1;
        for (let i = 0; i < this.numEmbeddings; i++) {
            const track = this.metadata[i];
            if (track[0].toLowerCase() === currentTitle.toLowerCase() && track[1].toLowerCase() === currentArtist.toLowerCase()) {
                pos = i;
                break;
            }
        }

        if (pos === -1) {
            for (let i = 0; i < this.numEmbeddings; i++) {
                const track = this.metadata[i];
                if (track[0].toLowerCase() === currentTitle.toLowerCase()) {
                    pos = i;
                    break;
                }
            }
        }

        // Get 104-dimensional features
        const queryFeatures = new Float32Array(this.featureDim);
        if (pos === -1) {
            // Default to mean features of dataset if song not found
            queryFeatures.set(this.meanFeatures);
        } else {
            const offset = pos * this.featureDim;
            for (let j = 0; j < this.featureDim; j++) {
                queryFeatures[j] = this.X_features[offset + j];
            }
        }

        // Apply emotion mappings on continuous audio features
        queryFeatures[1] = queryFeatures[1] * (0.4 + 0.6 * A); // energy
        queryFeatures[2] = queryFeatures[2] * (0.4 + 0.6 * A); // loudness
        queryFeatures[4] = Math.min(queryFeatures[4] + (1.0 - queryFeatures[4]) * 0.5 * (1.0 - A), 0.95); // acousticness
        queryFeatures[3] = queryFeatures[3] * (1.0 - 0.6 * A); // speechiness
        queryFeatures[7] = Math.min(queryFeatures[7] + (1.0 - queryFeatures[7]) * 0.4 * P, 0.95); // valence

        // Run the ONNX encoder model to project query features into the 16D latent space
        const tensorInput = new ort.Tensor('float32', queryFeatures, [1, this.featureDim]);
        const feeds = { input: tensorInput };
        const results = await this.session.run(feeds);
        const queryLatent = results.output.data; // Float32Array of size 16

        // Compute cosine similarities against all latent embeddings in the database
        const similarities = this.cosineSimilarity(queryLatent);

        // Exploration vs Exploitation noise scaling (linked to valence/pleasure)
        const explorationWeight = 1.0 - P;
        if (explorationWeight > 0) {
            for (let i = 0; i < this.numEmbeddings; i++) {
                similarities[i] += randomNormal(0, 0.05 * explorationWeight);
            }
        }

        // Sort indices based on similarity
        const indexedSimilarities = Array.from(similarities).map((val, idx) => ({ idx, val }));
        indexedSimilarities.sort((a, b) => b.val - a.val);

        // Find recommendations
        const recommendations = [];
        const queue = [];
        for (let item of indexedSimilarities) {
            if (item.idx === pos) continue; // Skip current song itself
            const recSong = this.metadata[item.idx];
            const songString = `${recSong[0]} - ${recSong[1]}`;

            if (excluded.includes(songString)) continue; // Skip recently played

            recommendations.push({
                name: recSong[0],
                artist: recSong[1],
                similarity: item.val
            });
            queue.push(recSong[2]); // Spotify ID

            if (recommendations.length >= topK) break;
        }

        return { recommendations, queue };
    }

    /**
     * Computes cosine similarity between query latent vector and all database embeddings.
     */
    cosineSimilarity(query) {
        const similarities = new Float32Array(this.numEmbeddings);
        
        let queryNorm = 0;
        for (let i = 0; i < this.latentDim; i++) {
            queryNorm += query[i] * query[i];
        }
        queryNorm = Math.sqrt(queryNorm);
        
        if (queryNorm === 0) return similarities;

        for (let i = 0; i < this.numEmbeddings; i++) {
            let dotProduct = 0;
            let embNorm = 0;
            const offset = i * this.latentDim;
            for (let j = 0; j < this.latentDim; j++) {
                const val = this.latentEmbeddings[offset + j];
                dotProduct += query[j] * val;
                embNorm += val * val;
            }
            embNorm = Math.sqrt(embNorm);
            if (embNorm === 0) {
                similarities[i] = 0;
            } else {
                similarities[i] = dotProduct / (queryNorm * embNorm);
            }
        }
        return similarities;
    }
}
