import os
import json
from openai import OpenAI

# Carrega produtos
PRODUTOS_DB_PATH = os.path.join(os.path.dirname(__file__), "produtos.json")
try:
    with open(PRODUTOS_DB_PATH, 'r', encoding='utf-8') as f:
        BASE_DE_PRODUTOS = json.load(f)
except Exception as e:
    print(f"Erro ao carregar produtos: {e}")
    BASE_DE_PRODUTOS = []

# Cliente xAI (Grok)
try:
    client = OpenAI(
        api_key=os.environ.get("XAI_API_KEY"),
        base_url="https://api.x.ai/v1"
    )
except:
    client = None

SYSTEM_PROMPT_TEMPLATE = """
Você é um assistente sênior de farmácia. 
Atendente Responsável: {atendente}

Analise a transcrição e sugira um produto da lista.
Responda ESTRITAMENTE em formato JSON.

LISTA DE PRODUTOS:
{json_produtos}

FORMATO DE RESPOSTA (JSON):
{{
  "sugestao": "Nome do Produto" (ou null),
  "explicacao": "Explicação curta e técnica para o atendente {atendente}."
}}
"""

def analisar_texto(texto: str, nome_funcionario: str = "Balconista") -> str | None:
    if not client or not BASE_DE_PRODUTOS:
        return None
        
    try:
        produtos_str = json.dumps(BASE_DE_PRODUTOS, ensure_ascii=False)
        prompt = SYSTEM_PROMPT_TEMPLATE.format(
            atendente=nome_funcionario,
            json_produtos=produtos_str
        )

        response = client.chat.completions.create(
            model="grok-4-1-fast-non-reasoning", 
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": texto}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content

    except Exception as e:
        print(f"Erro Grok: {e}")
        return None