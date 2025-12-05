import os
import json
from openai import OpenAI

# Carrega produtos (Mantido igual)
PRODUTOS_DB_PATH = os.path.join(os.path.dirname(__file__), "produtos.json")
try:
    with open(PRODUTOS_DB_PATH, 'r', encoding='utf-8') as f:
        BASE_DE_PRODUTOS = json.load(f)
except Exception as e:
    print(f"Erro ao carregar produtos: {e}")
    BASE_DE_PRODUTOS = []

# --- CONFIGURAÇÃO GROK (xAI) ---
# O Grok usa a SDK da OpenAI mas com a base_url da xAI
try:
    client = OpenAI(
        api_key=os.environ.get("XAI_API_KEY"), # Certifique-se que o .env tem XAI_API_KEY
        base_url="https://api.x.ai/v1"
    )
except Exception as e:
    print(f"Erro client Grok: {e}")
    client = None

SYSTEM_PROMPT_TEMPLATE = """
Você é um assistente de farmácia. Analise a transcrição e sugira um produto da lista.
Responda ESTRITAMENTE em formato JSON.

LISTA DE PRODUTOS:
{json_produtos}

FORMATO DE RESPOSTA (JSON):
{{
  "sugestao": "Nome do Produto" (ou null se nenhum for relevante),
  "explicacao": "Uma frase curta explicando o porquê da sugestão baseada nos sintomas."
}}

Se não houver recomendação, retorne "sugestao": null.
"""

def analisar_texto(texto: str) -> str | None:
    if not client or not BASE_DE_PRODUTOS:
        return None
        
    try:
        produtos_str = json.dumps(BASE_DE_PRODUTOS, ensure_ascii=False)
        prompt = SYSTEM_PROMPT_TEMPLATE.format(json_produtos=produtos_str)

        response = client.chat.completions.create(
            model="grok-beta", # Ou o modelo atual do Grok que vocês têm acesso
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": texto}
            ],
            temperature=0.1,
            response_format={"type": "json_object"} # Força JSON
        )
        
        content = response.choices[0].message.content
        # Retorna o JSON cru (string) para o server fazer o parse ou repassar
        return content

    except Exception as e:
        print(f"Erro Grok: {e}")
        return None