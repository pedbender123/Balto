
import numpy as np
import librosa

def extract_features(pcm_data: bytes, sample_rate: int = 16000):
    """
    Extracts audio features from PCM data:
    - Pitch (F0) Mean/Std
    - Spectral Centroid Mean
    """
    try:
        # Convert PCM bytes to float32 numpy array (-1.0 to 1.0)
        # Assuming PCM is 16-bit signed integer
        audio_int16 = np.frombuffer(pcm_data, dtype=np.int16)
        y = audio_int16.astype(np.float32) / 32768.0

        if len(y) < 512:
            return {
                "pitch_mean": 0.0,
                "pitch_std": 0.0,
                "spectral_centroid_mean": 0.0
            }

        # 1. Spectral Centroid (Brightness)
        cent = librosa.feature.spectral_centroid(y=y, sr=sample_rate)
        centroid_mean = float(np.mean(cent))

        # 2. Pitch (Fundamental Frequency F0) using Yin algorithm
        # F0 range for human speech: 50Hz to 300Hz (broadly)
        f0 = librosa.yin(y, fmin=50, fmax=400, sr=sample_rate)
        
        # Filter valid pitches (Yin can return wild values on silence/noise)
        # But we accept whatever librosa gives for now, or maybe filter NaN
        f0 = f0[~np.isnan(f0)]
        
        if len(f0) > 0:
            pitch_mean = float(np.mean(f0))
            pitch_std = float(np.std(f0))
        else:
            pitch_mean = 0.0
            pitch_std = 0.0

        return {
            "pitch_mean": pitch_mean,
            "pitch_std": pitch_std,
            "spectral_centroid_mean": centroid_mean
        }

    except Exception as e:
        print(f"[AudioAnalysis] Error: {e}")
        return {
            "pitch_mean": 0.0,
            "pitch_std": 0.0,
            "spectral_centroid_mean": 0.0
        }
