
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
        # Lista expandida de termos irrelevantes ou alucinações de ruído (ASR)
        ignored_substrings = [
            "(sons de passos)", 
            "(ruído)", 
            "(corte de vídeo)", 
            "(som de batida)",
            "(som de fundo)",
            "(música)",
            "(respiração)",
            "(tosse)",
            "(vento)",
            "leggendas",
            "legendas",
            "inscreva-se",
            "deixe seu like",
            "obrigado por assistir"
        ]
        
        # Alucinações comuns curtas (Whisper/ASR) que não devem engatilhar a IA se aparecerem sozinhas
        hallucinations_exact = [
            "obrigado.", "obrigada.", "obrigado", "obrigada",
            "tchau.", "tchau",
            "amém.", "amem.", "amém",
            "olá.", "ola.", "olá",
            "e aí.",
            "até mais.", "ate a proxima",
            "silêncio", "(silêncio)"
        ]
        
        clean = text.strip()
        
        # Filtro simples: se o texto for vazio
        if not clean:
            return

        clean_lower = clean.lower()
        
        # Filtro 1: Match exato de alucinações comuns (case-insensitive)
        if clean_lower in hallucinations_exact:
            return
            
        # Filtro 2: Verifica se o texto contém algum dos termos ignorados (substrings)
        if any(ign in clean_lower for ign in ignored_substrings):
             # Se for APENAS o ruído, ignora. Se tiver fala junto, mantemos (mas o prompt vai limpar)
             if len(clean) < 30: # Heuristica: texto curto que match com ruído/legenda é lixo
                 return
                 
        # Filtro 3: Textos extremamente curtos (1 palavra) que não significam nada sozinhos ("é.", "tá.", "ah.")
        words = clean.split()
        if len(words) == 1 and len(clean) <= 4:
            return
            
        # Filtro 4: Repetições bizarras de ASR (ex: "obrigado obrigado obrigado obrigado")
        unique_words = set(words)
        if len(unique_words) <= 2 and len(words) >= 4:
            return

        # Capture gap BEFORE adding
        now = time.time()
        self.last_gap = now - self.last_update_time
        self.last_update_time = now
        self.last_segment_word_count = len(words)

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
