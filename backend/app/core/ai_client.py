
import json
from openai import OpenAI
from app.core import config, prompts

class AIClient:
    def __init__(self):
        self.client = None
        if config.OPENAI_API_KEY:
            self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        else:
            print("[AI] OpenAI client not initialized (Missing API Key)")

    def analisar_texto(self, texto: str) -> str | None:
        if not self.client:
            return None
            
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.1,
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

# Singleton instance
ai_client = AIClient()
