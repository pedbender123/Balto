
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

        self.buffer.append(clean)

    def should_process(self) -> bool:
        if not self.buffer: return False
        word_count = len(" ".join(self.buffer).split())
        time_elapsed = time.time() - self.last_send_time
        return word_count >= self.min_words or time_elapsed >= self.max_wait_seconds

    def get_context_and_clear(self) -> str:
        full_text = " ".join(self.buffer)
        self.buffer = []
        self.last_send_time = time.time()
        return full_text
