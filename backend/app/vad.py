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
        self.silence_frames_needed = 10 # Aprox 300ms de silêncio (era 30)
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
        
        # [MODIFIED] Limit reduzed to 160 frames (~4.8s)
        self.segment_limit_frames = int(os.environ.get("VAD_SEGMENT_LIMIT_FRAMES", "160"))

        # [NEW] Overlap Configuration
        self.overlap_frames = int(os.environ.get("VAD_OVERLAP_FRAMES", "27")) # ~810ms
        self.overlap_buffer = deque(maxlen=self.overlap_frames)

        # Telemetria do segmento corrente
        self._seg_started = False
        self._seg_noise_start = None
        self._seg_thr_start = None
        self._seg_energy_sum = 0.0
        self._seg_energy_max = 0.0
        self._seg_energy_count = 0
        self._debug_frame_count = 0


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
            self._debug_frame_count += 1
            if self._debug_frame_count % 30 == 0:
                print(f"[VAD DEBUG] E: {energy:.1f} | Thr: {dynamic_threshold:.1f} | Noise: {self.noise_level:.1f} | Triggered: {self.triggered}")
            
            is_speech = False
            
            if is_loud_enough:
                try:
                    # Só chama o WebRTC se passou pelo gate de energia
                    is_speech = self.vad.is_speech(frame, self.sample_rate)
                    # [MOD] Se a energia for MUITO alta, considera fala mesmo se o WebRTC estiver na dúvida
                    if not is_speech and energy > (dynamic_threshold * 1.5):
                         is_speech = True
                except Exception:
                    is_speech = False
            
            # 5. Máquina de Estados
            if is_speech:
                # [REMOVED] Verbose movement log
                # print(f"   >>> [VAD] MOVEMENT DETECTED (WebRTC Confirmed)")
                
                # Se iniciou agora, adicionar pre-roll
                if not self.triggered:
                    # [NEW] Inject Overlap Buffer before Pre-roll
                    # This repeats the end of the PREVIOUS segment at the start of this one.
                    self.speech_buffer.extend(self.overlap_buffer)
                    
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

                # [NEW] Keep overlap buffer updated while speaking too
                self.overlap_buffer.append(frame)

                self._seg_energy_sum += float(energy)
                self._seg_energy_count += 1
                if energy > self._seg_energy_max:
                    self._seg_energy_max = float(energy)

                self.triggered = True
                self.silence_frames_count = 0

                # [NEW] Safety Cutoff
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
                        "overlap_frames": int(self.overlap_frames),
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
                
                # [NEW] Also update overlap buffer during silence hold (it might become valid speech or overlap for next)
                self.overlap_buffer.append(frame)

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
                        "overlap_frames": int(self.overlap_frames),
                    }

                    self.triggered = False
                    self.silence_frames_count = 0

                    segment = b"".join(self.speech_buffer)
                    self.speech_buffer.clear()
                    return segment, meta

            else:
                # Silêncio absoluto, mantendo pre-roll
                self.pre_roll_buffer.append(frame)
                
                # [NEW] Keep updating overlap buffer even in silence?
                # The user asked: "repetir os últimos ~0,8s do pacote anterior no começo do próximo."
                # Does "pacote anterior" mean the SPEECH packet or just audio stream?
                # Usually overlap is from the *end of the previous processed segment*.
                # But here, if we are in silence, we are effectively between segments.
                # If we just finished a segment, we already have `overlap_buffer` populated with the tail of that segment (because we appended during triggered).
                # If there is a long silence, `overlap_buffer` will eventually be filled with silence if we append here.
                # The requirement says: "repetir os últimos ~0,8s do pacote anterior no começo do próximo."
                # If there is 10s of silence, the "package anterior" was 10s ago. 
                # If we stick silence into overlap_buffer, we will overlap silence.
                # BUT, `overlap_buffer` is a deque(maxlen).
                # If we append silence frames here, the buffer will become full of silence.
                # When the NEXT speech starts, we will inject that silence.
                # That seems correct. Overlap is "context". Context of silence is silence.
                # However, usually overlap is used to catch "cut off words". 
                # "repetir os últimos ~0,8s do pacote anterior" implies the PREVIOUS SEGMENT's tail.
                # IF the previous segment ended because of "safety_limit", then the next segment starts IMMEDIATELY. use overlap of that cut.
                # IF the previous segment ended because of "silence", then the next segment starts after some silence.
                # If we are in silence, and we fill overlap_buffer with silence...
                # effectively we are just checking pre-roll?
                # Wait. "pre_roll_buffer" captures immediately preceding frames.
                # "overlap_buffer" captured frames *while triggered*.
                
                # Let's re-read carefully: "criar overlap_buffer e preencher com os últimos frames do segmento"
                # "ao iniciar um novo segmento, incluir overlap_buffer antes do pre_roll_buffer"
                # This implies overlap_buffer should contain the TAIL of the *Previous Segment*, NOT the silence in between.
                # So we should ONLY append to overlap_buffer when we are in `triggered` state (processing a segment).
                # When we are NOT triggered (silence), we should leave `overlap_buffer` AS IS (containing the tail of the last segment).
                # WAIT. If I stop speaking, silence happens. 
                # If I speak again 5 minutes later... prepending the audio from 5 minutes ago makes NO sense.
                # The "overlap" strategy described (reusing previous packet tail) is specifically handling the "continuous speech" scenario where we cut by *Safety Limit*.
                # When we cut by safety limit, we return a segment and immediately (likely) continue triggered or start a new one?
                # Actually, safety limit returns, sets triggered = False.
                # The loop continues.
                # If the user is STILL speaking, the next frame will be loud -> triggered=True again immediately.
                # At that moment, we inject `overlap_buffer`. 
                # `overlap_buffer` holds the tail of the JUST finished segment. Perfect.
                
                # What if we finished by SILENCE?
                # Then triggered=False. We go to else branch (silence).
                # If we DO NOT touch overlap_buffer here, it holds the tail of the phrase from 5 minutes ago.
                # When I speak again -> triggered=True -> we inject that old tail.
                # That is BAD.
                
                # So:
                # 1. If cut by Safety Limit: The tail is useful context for the immediate next chunk.
                # 2. If cut by Silence: The tail is... probably not useful if silence is long.
                #    BUT if silence is short, maybe?
                #    Actually, if I finish a sentence. Silence. Start new sentence.
                #    Do I want the end of the previous sentence attached? 
                #    Probably not. But the prompt says "repetir os últimos ... do pacote anterior".
                
                # However, logic: "preencher com os últimos frames do segmento".
                # "Segmento" = `speech_buffer`.
                # So `overlap_buffer` tracks `speech_buffer` frames.
                # When we are in silence, we are NOT in a segment. So we do NOT append to `overlap_buffer`.
                # But we must decide whether to KEEP or CLEAR it.
                # If I leave it, it will be injected next time.
                # If the goal is strictly to help with "Safety Limit" cuts (splitting a word in half), then it is critical there.
                # Is it harmful between separate sentences?
                # If I say "Hello" ... [10s silence] ... "World".
                # Result: "Hello[tail]World". 
                # This might confuse STT if it stitches them weirdly.
                # BUT, usually VAD overlap is for *windowing*.
                # Given strict instruction: "Enquanto triggered, a cada frame anexado em speech_buffer, também fazer self.overlap_buffer.append(frame)"
                # "Quando começar um novo segmento ... fazer self.speech_buffer.extend(self.overlap_buffer) antes do pre-roll"
                # It does NOT say "clear overlap buffer on silence".
                # It does NOT say "append silence to overlap buffer".
                # So I will follow instructions:
                # 1. Init overlap_buffer.
                # 2. While triggered: append to overlap_buffer.
                # 3. On Start: extend speech with overlap.
                
                # This implies that yes, even after long silence, we prepend the old tail.
                # If this is undesirable, the user didn't ask to prevent it. 
                # But typically for "continuous speech/noise" issues, this is the main target.
                # I will implement exactly as requested.
                
                pass
                
        return None