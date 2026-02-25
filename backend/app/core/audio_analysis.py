
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
        f0 = librosa.yin(y, fmin=50, fmax=400, sr=sample_rate)
        f0 = f0[~np.isnan(f0)]
        
        if len(f0) > 0:
            pitch_mean = float(np.mean(f0))
            pitch_std = float(np.std(f0))
        else:
            pitch_mean = 0.0
            pitch_std = 0.0

        # --- New Extended Metrics ---
        
        # 3. Zero Crossing Rate (ZCR)
        zcr = librosa.feature.zero_crossing_rate(y)
        zcr_mean = float(np.mean(zcr))

        # 4. Energy & dBFS
        # RMS Energy
        rmse = librosa.feature.rms(y=y)
        energy_rms_mean = float(np.mean(rmse))
        energy_rms_max = float(np.max(rmse))
        
        # Peak dBFS (assuming float32 -1.0 to 1.0, reference=1.0)
        # Avoid log(0)
        peak_amp = np.max(np.abs(y))
        if peak_amp > 0:
            peak_dbfs = float(20 * np.log10(peak_amp))
        else:
            peak_dbfs = -96.0 # Silence floor

        # 5. Clipping Ratio
        # Count samples close to 1.0 or -1.0 (threshold 0.995)
        clipping_count = np.sum(np.abs(y) > 0.995)
        clipping_ratio = float(clipping_count / len(y))

        # 6. DC Offset
        dc_offset = float(np.mean(y))

        # 7. Band Energy (Low/Mid/High)
        # Simple FFT-based band energy
        S = np.abs(librosa.stft(y))
        freqs = librosa.fft_frequencies(sr=sample_rate)
        
        # Define bands
        # Low: 0-250Hz, Mid: 250-4000Hz, High: 4000-8000Hz (Nyquist)
        # Find indices
        idx_low = (freqs <= 250)
        idx_mid = (freqs > 250) & (freqs <= 4000)
        idx_high = (freqs > 4000)

        # Sum energy in bands (mean across time)
        # S is Magnitude, Energy ~ S^2
        S_energy = S**2
        
        band_energy_low = float(np.mean(np.sum(S_energy[idx_low, :], axis=0)))
        band_energy_mid = float(np.mean(np.sum(S_energy[idx_mid, :], axis=0)))
        band_energy_high = float(np.mean(np.sum(S_energy[idx_high, :], axis=0)))

        # 8. SNR Estimate (Very Basic)
        # Estimate noise floor dynamically using the 10th percentile of RMSE energy frames
        # This is a rough approximation for a single segment
        rmse_flat = rmse.flatten()
        if len(rmse_flat) > 0:
            noise_floor_rms = np.percentile(rmse_flat, 10)
            signal_peak_rms = np.max(rmse_flat)
            if noise_floor_rms > 0:
                snr_estimate = float(20 * np.log10(signal_peak_rms / noise_floor_rms))
            else:
                snr_estimate = 0.0 # Clean/Silence
        else:
            snr_estimate = 0.0

        return {
            "pitch_mean": pitch_mean,
            "pitch_std": pitch_std,
            "spectral_centroid_mean": centroid_mean,
            
            "zcr": zcr_mean,
            "energy_rms_mean": energy_rms_mean,
            "energy_rms_max": energy_rms_max,
            "peak_dbfs": peak_dbfs,
            "clipping_ratio": clipping_ratio,
            "dc_offset": dc_offset,
            "band_energy_low": band_energy_low,
            "band_energy_mid": band_energy_mid,
            "band_energy_high": band_energy_high,
            "snr_estimate": snr_estimate
        }

    except Exception as e:
        print(f"[AudioAnalysis] Error: {e}")
        return {
            "pitch_mean": 0.0,
            "pitch_std": 0.0,
            "spectral_centroid_mean": 0.0
        }

# Alias for backward compatibility
extract_advanced_features = extract_features

def classify_audio(features: dict) -> str:
    """
    Classifica o áudio em: fala, ruido, fala_com_ruido, silencio_com_ruido.
    Baseado nas heurísticas do Balto 3.0.
    """
    snr = features.get("snr_estimate", 0.0)
    pitch = features.get("pitch_mean", 0.0)
    zcr = features.get("zcr", 0.0)
    energy = features.get("energy_rms_mean", 0.0)
    
    # Heurística:
    # 1. Fala Limpa: SNR alto e Pitch detectado
    if snr > 12.0 and pitch > 0:
        return "fala"
    
    # 2. Fala com Ruído: SNR moderado mas Pitch detectado
    if snr > 5.0 and pitch > 0:
        return "fala_com_ruido"
    
    # 3. Ruído: ZCR alto ou SNR baixo sem Pitch
    if zcr > 0.15 or (snr < 5.0 and pitch == 0):
        # Se tiver energia baixíssima, é silêncio ruidoso
        if energy < 0.005:
            return "silencio_com_ruido"
        return "ruido"
        
    # Default fallback
    if pitch > 0:
        return "fala"
    return "ruido"

def warmup():
    """
    Executes a dummy extraction to force library loading (librosa/numba JIT)
    at startup, avoiding latency on the first real request.
    """
    print("[AudioAnalysis] Warming up librosa/numba...")
    try:
        # 16k mono silent frame (1024 samples)
        dummy_audio = b'\x00' * 2048
        extract_features(dummy_audio)
    except Exception as e:
        print(f"[AudioAnalysis] Warmup failed (non-critical): {e}")

