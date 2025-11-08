import webrtcvad
from collections import deque

class VAD:
    """
    Implementa a Detecção de Atividade de Voz (VAD) de forma 'stateful'.
    Recebe chunks de áudio e retorna um bloco de bytes maior quando
    detecta um segmento completo de fala.
    Baseado nas fontes 93-102.
    """
    
    def __init__(self, sample_rate=16000, frame_duration_ms=30, vad_aggressiveness=1):
        """
        Inicializa o VAD.
        O formato de áudio (16kHz, 16-bit) é crítico (fonte 40, 95).
        webrtcvad requer durações de frame de 10, 20 ou 30 ms.
        """
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        
        # --- A CORREÇÃO ESTÁ AQUI ---
        # (sample_rate * (frame_duration_ms // 1000) * 2) -> BUG (dava 0)
        self.frame_bytes = (sample_rate * frame_duration_ms // 1000) * 2 # CORRETO (dá 960)
        
        self.vad = webrtcvad.Vad(vad_aggressiveness)
        
        self.audio_buffer = bytearray()
        self.speech_buffer = deque()
        self.triggered = False
        self.silence_frames_needed = 10 # N. de frames de silêncio para "cortar" a fala
        self.silence_frames_count = 0

    def process(self, audio_chunk: bytes) -> bytes | None:
        """
        Processa um chunk de áudio vindo do cliente.
        Acumula áudio e retorna o segmento de fala quando detecta uma pausa.
        """
        self.audio_buffer.extend(audio_chunk)
        
        while len(self.audio_buffer) >= self.frame_bytes:
            frame = self.audio_buffer[:self.frame_bytes]
            del self.audio_buffer[:self.frame_bytes]
            
            try:
                is_speech = self.vad.is_speech(frame, self.sample_rate)
            except Exception:
                # Pode falhar se o frame não tiver o tamanho exato
                is_speech = False

            if is_speech:
                self.speech_buffer.append(frame)
                self.triggered = True
                self.silence_frames_count = 0
            elif self.triggered:
                # Estamos em silêncio, mas estávamos falando
                self.silence_frames_count += 1
                if self.silence_frames_count >= self.silence_frames_needed:
                    # Fim da fala detectado (fonte 102)
                    self.triggered = False
                    self.silence_frames_count = 0
                    
                    # Concatena os frames de fala e retorna
                    speech_segment = b''.join(self.speech_buffer)
                    self.speech_buffer.clear()
                    return speech_segment
            else:
                # Silêncio contínuo, não faz nada
                pass
        
        # Nenhum segmento de fala completo foi retornado ainda
        return None