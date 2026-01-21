import numpy as np
import noisereduce as nr
import logging

# Configuração básica de logging local
logger = logging.getLogger(__name__)

class AudioCleaner:
    def __init__(self, sample_rate=16000, stationary=True, prop_decrease=0.85):
        self.sample_rate = sample_rate
        self.stationary = stationary
        self.prop_decrease = prop_decrease
        # Buffer opcional se precisarmos de contexto (por enquanto, stateless per chunk para performance)
        # No futuro, pode-se manter um perfil de ruído persistente

    def process(self, audio_bytes: bytes) -> bytes:
        """
        Recebe bytes PCM 16-bit e retorna o áudio limpo em bytes PCM 16-bit.
        """
        if not audio_bytes:
            return b""

        try:
            # Converter bytes para numpy array (int16)
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16)

            # Para chunks muito pequenos, noisereduce pode falhar ou ser ineficiente.
            # Se for muito pequeno, retorna original.
            if len(audio_data) < 512:
                return audio_bytes

            # Redução de ruído estacionário
            # prop_decrease=0.5 reduz o ruído em 50% para evitar artefatos robóticos excessivos
            reduced_noise = nr.reduce_noise(
                y=audio_data, 
                sr=self.sample_rate, 
                stationary=self.stationary,
                prop_decrease=self.prop_decrease, # Agressividade da limpeza
                n_fft=1024,         # FFT menor para performance em chunks menores
                n_std_thresh_stationary=1.5
            )

            # Calculate Gain (Reduction) in dB
            # Gain = 10 * log10(Energy_Out / Energy_In)
            energy_in = np.sum(audio_data.astype(np.float32) ** 2)
            energy_out = np.sum(reduced_noise.astype(np.float32) ** 2)
            
            if energy_in > 0 and energy_out > 0:
                self.last_gain_db = float(10 * np.log10(energy_out / energy_in))
            else:
                self.last_gain_db = 0.0

            # Converter de volta para bytes (int16)
            return reduced_noise.astype(np.int16).tobytes()

        except Exception as e:
            logger.error(f"Erro no AudioCleaner: {e}")
            # Em caso de falha, fail-safe retorna o áudio original
            return audio_bytes
