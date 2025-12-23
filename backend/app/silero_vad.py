import torch
import numpy as np

class SileroVAD:
    def __init__(self, sample_rate=16000, threshold=0.5):
        self.sample_rate = sample_rate
        self.threshold = threshold
        
        print("[SileroVAD] Carregando modelo...")
        self.model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                           model='silero_vad',
                                           force_reload=False,
                                           trust_repo=True)
        
        (self.get_speech_timestamps, 
         self.save_audio, 
         self.read_audio, 
         self.VADIterator, 
         self.collect_chunks) = utils
         
        self.model.reset_states()
        print("[SileroVAD] Modelo carregado.")

    def process_full_audio(self, audio_data: bytes):
        """
        Processa um arquivo de áudio inteiro (bytes PCM 16-bit 16kHz Mono)
        e retorna uma lista de timestamps de fala [{'start': int, 'end': int}, ...].
        Os timestamps são em AMOSTRAS (samples).
        """
        # Converter bytes PCM int16 para float32 normalizado (-1.0 a 1.0)
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        audio_tensor = torch.Tensor(audio_np)
        
        timestamps = self.get_speech_timestamps(
            audio_tensor, 
            self.model, 
            sampling_rate=self.sample_rate,
            threshold=self.threshold
        )
        return timestamps
    
    def get_speech_segments(self, audio_data: bytes):
        """
        Retorna uma lista de BYTES, cada um sendo um segmento de fala.
        """
        timestamps = self.process_full_audio(audio_data)
        segments = []
        
        # Como timestamps são relativos ao array de floats, convertemos de volta para bytes
        # Cada sample int16 tem 2 bytes.
        
        for ts in timestamps:
            start_byte = int(ts['start']) * 2
            end_byte = int(ts['end']) * 2
            segments.append(audio_data[start_byte:end_byte])
            
        return segments

    def get_iterator(self):
        """Retorna uma instância de VADIterator para streaming."""
        return self.VADIterator(self.model, threshold=self.threshold, sampling_rate=self.sample_rate)
