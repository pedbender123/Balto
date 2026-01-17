
import time

class TranscriptionBuffer:
    """
    Acumula transcrições parciais. Só libera para a IA quando:
    1. Atinge X palavras (ex: 10) OU
    2. Passa Y segundos (ex: 5) sem novas falas.
    """
    def __init__(self, min_words=10, max_wait_seconds=5):
        self.buffer = []
        self.min_words = min_words
        self.max_wait_seconds = max_wait_seconds
        self.last_send_time = time.time()
        
        # New State for Gaps
        self.last_update_time = time.time()
        self.last_gap = 0.0
        self.last_segment_word_count = 0
        
    def add_text(self, text: str):
        # Lista expandida de termos irrelevantes ou alucinações de ruído
        ignored_substrings = [
            "(sons de passos)", 
            "(ruído)", 
            "(corte de vídeo)", 
            "(som de batida)",
            "(som de fundo)",
            "(música)",
            "(respiração)",
            "(tosse)", # Tosse isolada sem fala pode ser ignorada no buffer se for recorrente como ruído
            "(vento)"
        ]
        
        clean = text.strip()
        
        # Filtro simples: se o texto for exatamente um dos ignorados ou muito curto/vazio
        if not clean:
            return

        # Verifica se o texto contém algum dos termos ignorados (normalizado para lower)
        clean_lower = clean.lower()
        if any(ign in clean_lower for ign in ignored_substrings):
             # Se for APENAS o ruído, ignora. Se tiver fala junto, mantemos (mas o prompt vai limpar)
             if len(clean) < 20: # Heuristica: texto curto que match com ruído é lixo
                 return

        # Capture gap BEFORE adding
        now = time.time()
        self.last_gap = now - self.last_update_time
        self.last_update_time = now
        self.last_segment_word_count = len(clean.split())

        self.buffer.append(clean)

    def should_process(self) -> bool:
        if not self.buffer: return False
        
        word_count = len(" ".join(self.buffer).split())
        time_since_last_send = time.time() - self.last_send_time
        
        # --- New Rules ---
        
        # Rule B: Suppress if > 45s gap AND <= 2 words
        # This prevents "Ok" or noises from triggering a process call after a long silence.
        is_very_long_gap = (self.last_gap > 45.0)
        if is_very_long_gap and self.last_segment_word_count <= 2:
            return False

        # Rule A: Trigger if > 5s gap AND > 3 words
        # This allows capturing a new full sentence immediately even if buffer < 10 words.
        is_long_gap = (self.last_gap > 5.0)
        if is_long_gap and self.last_segment_word_count > 3:
            return True

        # Standard Rules
        return word_count >= self.min_words or time_since_last_send >= self.max_wait_seconds

    def get_context_and_clear(self) -> str:
        full_text = " ".join(self.buffer)
        self.buffer = []
        self.last_send_time = time.time()
        return full_text
