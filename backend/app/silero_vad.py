import torch
import os
import numpy as np

class SileroVAD:
    def __init__(self, sample_rate=16000, threshold=0.5):
        self.sample_rate = sample_rate
        self.threshold = threshold
        
        print("[SileroVAD] Carregando modelo...")
        # Tenta carregar do diretório vendor local primeiro
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        local_model_dir = os.path.join(base_dir, 'vendor', 'silero-vad')
        
        repo_or_dir = 'snakers4/silero-vad'
        source = 'github'
        trust_repo = True
        
        if os.path.exists(local_model_dir):
            print(f"Carregando Silero VAD localmente de: {local_model_dir}")
            repo_or_dir = local_model_dir
            source = 'local'
            # trust_repo is not a valid argument for local source in older torch versions, but let's check.
            # actually torch.hub.load(source='local', ...) uses _load_local which doesn't take trust_repo usually, 
            # but hub.load might pass kwargs. Let's keep it but handle if it fails? 
            # No, safest to just pass it, hoping it ignores it or it's needed.
            # Wait, for source='local', trust_repo is not needed/used same way.
        else:
            print("Carregando Silero VAD do GitHub (cache)")

        # Prepare kwargs
        kwargs = {
            'model': 'silero_vad',
            'force_reload': False,
        }
        if source == 'github':
             kwargs['trust_repo'] = True
        
        self.model, utils = torch.hub.load(repo_or_dir=repo_or_dir, source=source, **kwargs)
        
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
