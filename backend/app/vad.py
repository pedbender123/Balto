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
    
    def __init__(self, sample_rate=16000, frame_duration_ms=30, vad_aggressiveness=3, threshold_multiplier=None, min_energy_threshold=None):
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
        self.silence_frames_needed = 30 # Aprox 900ms de silêncio (era 20/600ms)
        self.silence_frames_count = 0
        
        # --- Lógica Adaptativa (EMA) ---
        # Nível de ruído base inicial (será ajustado dinamicamente)
        self.noise_level = 100.0 
        # Fator Alpha: Quão rápido nos adaptamos? 
        # 0.05 = adaptação lenta (bom para ruído de fundo constante)
        self.alpha = 0.05
        
        # Fator de Segurança a partir de env ou parametro
        if threshold_multiplier is not None:
             self.threshold_multiplier = float(threshold_multiplier)
        else:
             self.threshold_multiplier = float(os.environ.get("VAD_THRESHOLD_MULTIPLIER", "1.8"))

        # Limite mínimo absoluto a partir de env ou parametro
        if min_energy_threshold is not None:
             self.min_energy_threshold = float(min_energy_threshold)
        else:
             self.min_energy_threshold = float(os.environ.get("VAD_MIN_ENERGY_THRESHOLD", "120.0"))
        
        self.pre_roll_buffer = deque(maxlen=20) # 600ms de pre-roll (pedido > 0.2s)

        self.vad_aggressiveness = vad_aggressiveness
        self.segment_limit_frames = 200  # mesmo valor do seu cutoff atual

        # Telemetria do segmento corrente
        self._seg_started = False
        self._seg_noise_start = None
        self._seg_thr_start = None
        self._seg_energy_sum = 0.0
        self._seg_energy_max = 0.0
        self._seg_energy_count = 0


    def _calculate_energy(self, frame):
        """Calcula a energia RMS (Root Mean Square) do frame."""
        return audioop.rms(frame, 2)

    def process(self, audio_chunk: bytes) -> tuple[bytes, dict] | None:
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

            # [REMOVED] Verbose Frame-by-frame log
            # print(f"[VAD LOG] ...")
            
            is_speech = False
            
            if is_loud_enough:
                try:
                    # Só chama o WebRTC se passou pelo gate de energia
                    is_speech = self.vad.is_speech(frame, self.sample_rate)
                except Exception:
                    is_speech = False
            
            # 5. Máquina de Estados
            if is_speech:
                # [REMOVED] Verbose movement log
                # print(f"   >>> [VAD] MOVEMENT DETECTED (WebRTC Confirmed)")
                
                # Se iniciou agora, adicionar pre-roll
                if not self.triggered:
                    self.speech_buffer.extend(self.pre_roll_buffer)
                    self.pre_roll_buffer.clear()
                    # segmento começou agora
                    self._seg_started = True
                    self._seg_noise_start = float(self.noise_level)
                    self._seg_thr_start = float(dynamic_threshold)
                    self._seg_energy_sum = 0.0
                    self._seg_energy_max = 0.0
                    self._seg_energy_count = 0

                self.speech_buffer.append(frame)

                self._seg_energy_sum += float(energy)
                self._seg_energy_count += 1
                if energy > self._seg_energy_max:
                    self._seg_energy_max = float(energy)

                self.triggered = True
                self.silence_frames_count = 0

                # [NEW] Safety Cutoff: 6 seconds limit
                # 6000ms / 30ms = 200 frames
                if len(self.speech_buffer) >= self.segment_limit_frames:
                    # print(f"[VAD WARN] SEGMENT LIMIT REACHED (6s). Forcing cut.")
                    cut_reason = "safety_limit"
                    noise_end = float(self.noise_level)
                    thr_end = float(dynamic_threshold)

                    energy_mean = (self._seg_energy_sum / self._seg_energy_count) if self._seg_energy_count else 0.0
                    meta = {
                        "frames_len": len(self.speech_buffer),
                        "cut_reason": cut_reason,
                        "silence_frames_count_at_cut": int(self.silence_frames_count),

                        "noise_level_start": self._seg_noise_start,
                        "noise_level_end": noise_end,
                        "dynamic_threshold_start": self._seg_thr_start,
                        "dynamic_threshold_end": thr_end,

                        "energy_rms_mean": float(energy_mean),
                        "energy_rms_max": float(self._seg_energy_max),

                        # snapshots params
                        "threshold_multiplier": float(self.threshold_multiplier),
                        "min_energy_threshold": float(self.min_energy_threshold),
                        "alpha": float(self.alpha),
                        "vad_aggressiveness": int(self.vad_aggressiveness),
                        "silence_frames_needed": int(self.silence_frames_needed),
                        "pre_roll_len": int(self.pre_roll_buffer.maxlen),
                        "segment_limit_frames": int(self.segment_limit_frames),
                    }

                    self.triggered = False
                    self.silence_frames_count = 0
                    segment = b"".join(self.speech_buffer)
                    self.speech_buffer.clear()
                    return segment, meta

            elif self.triggered:
                # Estava falando, agora parou (silêncio temporário ou fim de frase)
                self.silence_frames_count += 1
                self.speech_buffer.append(frame) # Mantém o "rabicho" do áudio
                
                # [REMOVED] Verbose silence hold log
                # print(f"   ... [VAD] Silence Hold ({self.silence_frames_count}/{self.silence_frames_needed})")

                if self.silence_frames_count >= self.silence_frames_needed:
                    print(f"[VAD] SEGMENT FINISHED ({len(self.speech_buffer)} frames)")

                    cut_reason = "silence_end"
                    noise_end = float(self.noise_level)
                    thr_end = float(dynamic_threshold)

                    # (opcional) acumula energy também nesses frames de rabicho:
                    self._seg_energy_sum += float(energy)
                    self._seg_energy_count += 1
                    if energy > self._seg_energy_max:
                        self._seg_energy_max = float(energy)

                    energy_mean = (self._seg_energy_sum / self._seg_energy_count) if self._seg_energy_count else 0.0

                    meta = {
                        "frames_len": len(self.speech_buffer),
                        "cut_reason": cut_reason,
                        "silence_frames_count_at_cut": int(self.silence_frames_count),

                        "noise_level_start": self._seg_noise_start,
                        "noise_level_end": noise_end,
                        "dynamic_threshold_start": self._seg_thr_start,
                        "dynamic_threshold_end": thr_end,

                        "energy_rms_mean": float(energy_mean),
                        "energy_rms_max": float(self._seg_energy_max),

                        "threshold_multiplier": float(self.threshold_multiplier),
                        "min_energy_threshold": float(self.min_energy_threshold),
                        "alpha": float(self.alpha),
                        "vad_aggressiveness": int(self.vad_aggressiveness),
                        "silence_frames_needed": int(self.silence_frames_needed),
                        "pre_roll_len": int(self.pre_roll_buffer.maxlen),
                        "segment_limit_frames": int(self.segment_limit_frames),
                    }

                    self.triggered = False
                    self.silence_frames_count = 0

                    segment = b"".join(self.speech_buffer)
                    self.speech_buffer.clear()
                    return segment, meta

            else:
                # Silêncio absoluto, mantendo pre-roll
                self.pre_roll_buffer.append(frame)
                
        return None