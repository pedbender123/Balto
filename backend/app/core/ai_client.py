import json
from openai import OpenAI
from app.core import config, prompts

class AIClient:
    def __init__(self):
        self.client = None
        if config.OPENAI_API_KEY:
            self.client = OpenAI(
                api_key=config.OPENAI_API_KEY,
                base_url=config.OPENAI_BASE_URL
            )
        else:
            print("[AI] OpenAI client not initialized (Missing API Key)")

    def analisar_texto(self, texto: str) -> str | None:
        if not self.client:
            return None
            
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.1,
                max_tokens=180,
                messages=[
                    {"role": "developer", "content": prompts.SYSTEM_PROMPT},
                    {"role": "user", "content": texto}
                ],
                response_format=prompts.RESPONSE_SCHEMA
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[AI] Error: {e}")
            return None


    def normalizar_texto(self, texto: str) -> str | None:
        if not self.client:
            return None
        if not texto or not texto.strip():
            return "NADA_RELEVANTE | OUTRO"

        try:
            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                temperature=0,
                messages=[
                    {"role": "system", "content": prompts.NORMALIZE_INSTRUCTIONS},
                    {"role": "user", "content": texto}
                ]
            )
            out = response.choices[0].message.content
            if out:
                return out.strip()
            return None

        except Exception as e:
            print(f"[AI][normalize] Error: {e}")
            return None

    def classificar_cesta(self, normalizado: str) -> dict:
        """
        Entrada: string tipo "MED:imosec | GASTRO"
        Saída: dict com macros_top2, micro_categoria, ancoras_para_excluir
        """
        if not self.client:
            return {"macros_top2": ["OUTRO", "OUTRO"], "micro_categoria": None, "ancoras_para_excluir": []}

        normalizado = (normalizado or "").strip()
        if not normalizado:
            normalizado = "NADA_RELEVANTE | OUTRO"

        try:
            response = self.client.chat.completions.create(
                model="gpt-4.1",
                temperature=0,
                messages=[
                    {"role": "system", "content": prompts.CLASSIFY_INSTRUCTIONS},
                    {"role": "user", "content": normalizado}
                ],
                response_format={"type": "json_object"}
            )

            out = response.choices[0].message.content
            out = (out or "").strip()
            if not out:
                raise ValueError("Empty classify output")

            return json.loads(out)

        except Exception as e:
            print(f"[AI][classify] Error: {e}")
            return {"macros_top2": ["OUTRO", "OUTRO"], "micro_categoria": None, "ancoras_para_excluir": []}

# Singleton instance
ai_client = AIClient()
