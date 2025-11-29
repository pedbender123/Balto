import webrtcvad
import audioop
from collections import deque
import os

class VAD:
    """
    Implementa Detecção de Atividade de Voz (VAD) com Filtro de Proximidade (Energy Gate).
    
    1. Energy Gate: Ignora sons baixos (distantes).
    2. WebRTC VAD: Identifica se o som alto é voz humana ou barulho.
    """
    
    def __init__(self, sample_rate=16000, frame_duration_ms=30, vad_aggressiveness=3):
        """
        vad_aggressiveness: 0 a 3. Usamos 3 (o mais agressivo) para filtrar ruídos estacionários.
        """
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_bytes = (sample_rate * frame_duration_ms // 1000) * 2
        
        # Inicializa o VAD do Google (WebRTC)
        self.vad = webrtcvad.Vad(vad_aggressiveness)
        
        self.audio_buffer = bytearray()
        self.speech_buffer = deque()
        self.triggered = False
        
        # Configurações de Silêncio
        self.silence_frames_needed = 15  
        self.silence_frames_count = 0
        

        self.energy_threshold = int(os.environ.get("VAD_ENERGY_THRESHOLD", 300))

    def _calculate_energy(self, frame):
        """Calcula a energia (RMS) do frame de áudio."""
        return audioop.rms(frame, 2) # 2 = sample width (16-bit)

    def process(self, audio_chunk: bytes) -> bytes | None:
        """
        Processa chunks, aplica filtro de energia e VAD.
        Retorna o segmento de fala completo quando finalizado.
        """
        self.audio_buffer.extend(audio_chunk)
        
        while len(self.audio_buffer) >= self.frame_bytes:
            frame = self.audio_buffer[:self.frame_bytes]
            del self.audio_buffer[:self.frame_bytes]
            
            # 1. Filtro de Proximidade (Energy Gate)
            energy = self._calculate_energy(frame)
            is_loud_enough = energy > self.energy_threshold
            
            is_speech = False
            
            # 2. Só roda o VAD se o áudio for alto o suficiente (perto)
            if is_loud_enough:
                try:
                    is_speech = self.vad.is_speech(frame, self.sample_rate)
                except Exception:
                    is_speech = False
            else:
                # Se for muito baixo, consideramos silêncio (mesmo que seja voz lá no fundo)
                is_speech = False

            # 3. Máquina de Estados (Trigger)
            if is_speech:
                self.speech_buffer.append(frame)
                self.triggered = True
                self.silence_frames_count = 0
            elif self.triggered:
                # Estamos em silêncio (ou voz distante), mas estávamos falando antes
                self.silence_frames_count += 1
                
                # Mantém um pouco de "silêncio" no buffer para a frase não ficar cortada abruptamente
                self.speech_buffer.append(frame)
                
                if self.silence_frames_count >= self.silence_frames_needed:
                    # Fim da fala detectado
                    self.triggered = False
                    self.silence_frames_count = 0
                    
                    # Concatena e retorna
                    speech_segment = b''.join(self.speech_buffer)
                    self.speech_buffer.clear()
                    return speech_segment
            else:
                # Silêncio contínuo e não disparado -> mantém buffer limpo ou 
                # guarda um pequeno buffer de pré-roll (opcional, aqui limpamos para economizar memória)
                pass
        
        return None