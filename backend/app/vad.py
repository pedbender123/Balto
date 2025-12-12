import webrtcvad
import audioop
from collections import deque
import os
import math

class VAD:
    """
    VAD Adaptativo (Fase 1 - Balto 2.0)
    
    Implementa um filtro de ruído dinâmico usando Média Móvel Exponencial (EMA).
    Isso permite que o sistema se adapte ao "Noise Floor" (ar condicionado, zumbido de geladeira)
    e só ative a transcrição quando houver um pico de energia real (voz).
    """
    
    def __init__(self, sample_rate=16000, frame_duration_ms=30, vad_aggressiveness=3):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_bytes = (sample_rate * frame_duration_ms // 1000) * 2
        
        # WebRTC VAD (Google) - Detecta voz humana
        self.vad = webrtcvad.Vad(vad_aggressiveness)
        
        # Buffers
        self.audio_buffer = bytearray()
        self.speech_buffer = deque()
        self.triggered = False
        
        # Configurações de Silêncio para "corte" da frase
        self.silence_frames_needed = 20 # Aprox 600ms de silêncio para considerar fim de frase
        self.silence_frames_count = 0
        
        # --- Lógica Adaptativa (EMA) ---
        # Nível de ruído base inicial (será ajustado dinamicamente)
        self.noise_level = 100.0 
        # Fator Alpha: Quão rápido nos adaptamos? 
        # 0.05 = adaptação lenta (bom para ruído de fundo constante)
        self.alpha = 0.05
        # Fator de Segurança: Voz tem que ser X vezes mais alta que o ruído
        self.threshold_multiplier = 1.5
        
        # Limite mínimo absoluto para evitar ativar com silêncio total
        self.min_energy_threshold = 200

    def _calculate_energy(self, frame):
        """Calcula a energia RMS (Root Mean Square) do frame."""
        return audioop.rms(frame, 2)

    def process(self, audio_chunk: bytes) -> bytes | None:
        """
        Processa o chunk de áudio aplicando o VAD Adaptativo.
        Retorna bytes de áudio (frase completa) se finalizou uma fala, ou None.
        """
        self.audio_buffer.extend(audio_chunk)
        
        while len(self.audio_buffer) >= self.frame_bytes:
            frame = self.audio_buffer[:self.frame_bytes]
            del self.audio_buffer[:self.frame_bytes]
            
            # 1. Calcular Energia Atual
            energy = self._calculate_energy(frame)
            
            # 2. Atualizar Nível de Ruído (EMA)
            # Se a energia for baixa (provável silêncio/fundo), atualizamos o noise_level
            # Se for muito alta (grito/fala forte), evitamos poluir a média de ruído
            if not self.triggered: 
                self.noise_level = (self.alpha * energy) + ((1 - self.alpha) * self.noise_level)
            
            # 3. Calcular Limiar Dinâmico
            dynamic_threshold = max(self.noise_level * self.threshold_multiplier, self.min_energy_threshold)
            
            # 4. Gate de Energia (Fase 1 Limpeza)
            is_loud_enough = energy > dynamic_threshold
            
            is_speech = False
            
            if is_loud_enough:
                try:
                    # Só chama o WebRTC se passou pelo gate de energia
                    is_speech = self.vad.is_speech(frame, self.sample_rate)
                except Exception:
                    is_speech = False
            
            # 5. Máquina de Estados
            if is_speech:
                self.speech_buffer.append(frame)
                self.triggered = True
                self.silence_frames_count = 0
            elif self.triggered:
                # Estava falando, agora parou (silêncio temporário ou fim de frase)
                self.silence_frames_count += 1
                self.speech_buffer.append(frame) # Mantém o "rabicho" do áudio
                
                if self.silence_frames_count >= self.silence_frames_needed:
                    # Fim de frase confirmado
                    self.triggered = False
                    self.silence_frames_count = 0
                    
                    segment = b''.join(self.speech_buffer)
                    self.speech_buffer.clear()
                    return segment
            else:
                # Silêncio absoluto, descarta frames para economizar memória
                # (Opcional: manter um pequeno buffer de pré-roll)
                pass
                
        return None