try:
    import webrtc_audio_processing as webrtc
except ImportError:
    webrtc = None

# Configuração básica de logging local
logger = logging.getLogger(__name__)

class WebRTCCleaner:
    """
    Usa o WebRTC Audio Processing (APC) para:
    - Automatic Gain Control (AGC)
    - Noise Suppression (NS)
    """
    def __init__(self, sample_rate=16000):
        if webrtc is None:
            raise ImportError("Biblioteca 'webrtc-audio-processing' não encontrada.")
        
        self.sample_rate = sample_rate
        # O WebRTC APM trabalha internamente com chunks de 10ms (160 samples @ 16kHz)
        self.apm = webrtc.AudioProcessingModule(
            enable_aec=False,
            enable_agc=True,
            enable_ns=True,
            enable_vad=False # Já temos nosso próprio VAD
        )
        
        # Configurar AGC
        # modo: 0 (Adaptive Analog), 1 (Adaptive Digital), 2 (Fixed Digital)
        self.apm.agc.mode = 1 
        self.apm.agc.target_level_dbfs = 3 # Mira em -3dBFS
        self.apm.agc.compression_gain_db = 9 # Pode subir até 9dB
        
        # Configurar NS
        # nível: 0 (Mild), 1 (Medium), 2 (High), 3 (Very High)
        self.apm.ns.level = 2

    def process(self, audio_bytes: bytes) -> bytes:
        """Processa o áudio através do APM."""
        # Se os bytes não forem múltiplos de 10ms, o APM pode reclamar ou ignorar o resto.
        # Nosso WebSocket envia chunks de 60ms (1920 bytes), o que é múltiplo de 10ms.
        return self.apm.process_stream(audio_bytes)

class AudioCleaner:
    def __init__(self, sample_rate=16000, stationary=True, prop_decrease=0.85):
        self.sample_rate = sample_rate
        self.stationary = stationary
        self.prop_decrease = prop_decrease
        self.last_gain_db = 0.0
        
        # Tenta inicializar o WebRTC Cleaner como prioridade
        self.webrtc_cleaner = None
        if webrtc:
            try:
                self.webrtc_cleaner = WebRTCCleaner(sample_rate)
                logger.info("WebRTCCleaner (AGC/NS) inicializado com sucesso.")
            except Exception as e:
                logger.warning(f"Falha ao carregar WebRTCCleaner: {e}. Usando fallback noisereduce.")

    def process(self, audio_bytes: bytes) -> bytes:
        """
        Recebe bytes PCM 16-bit e retorna o áudio limpo em bytes PCM 16-bit.
        Prioriza WebRTC. Fallback para noisereduce.
        """
        if not audio_bytes:
            return b""

        # 1. Tenta WebRTC (Tempo real, AGC, NS)
        if self.webrtc_cleaner:
            try:
                return self.webrtc_cleaner.process(audio_bytes)
            except Exception as e:
                logger.error(f"Erro no WebRTCCleaner: {e}")
                # Prossegue para fallback

        # 2. Fallback: noisereduce (Estatístico/Estacionário)
        try:
            # Converter bytes para numpy array (int16)
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16)

            # Para chunks muito pequenos, noisereduce pode falhar ou ser ineficiente.
            if len(audio_data) < 512:
                return audio_bytes

            # Redução de ruído estacionário
            reduced_noise = nr.reduce_noise(
                y=audio_data, 
                sr=self.sample_rate, 
                stationary=self.stationary,
                prop_decrease=self.prop_decrease,
                n_fft=1024,
                n_std_thresh_stationary=1.5
            )

            # Calculate Gain (Reduction) in dB
            energy_in = np.sum(audio_data.astype(np.float32) ** 2)
            energy_out = np.sum(reduced_noise.astype(np.float32) ** 2)
            
            if energy_in > 0 and energy_out > 0:
                self.last_gain_db = float(10 * np.log10(energy_out / energy_in))
            else:
                self.last_gain_db = 0.0

            return reduced_noise.astype(np.int16).tobytes()

        except Exception as e:
            logger.error(f"Erro no AudioCleaner (noisereduce): {e}")
            return audio_bytes
