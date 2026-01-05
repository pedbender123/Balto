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

# Cliente xAI (Grok)
try:
    client = OpenAI(
        api_key=os.environ.get("XAI_API_KEY"),
        base_url="https://api.x.ai/v1"
    )
except:
    client = None

# Configuração de Restrição de Produtos
# "1" = Limitado à lista de produtos (Strict)
# "0" = Livre, mas sem medicamentos controlados (Free)
RESTRICT_PRODUCTS = os.environ.get("RESTRICT_PRODUCTS", "1") == "1"

# Prompt Strict (Lista Fixa)
SYSTEM_PROMPT_TEMPLATE_STRICT = """
Você é um assistente sênior de farmácia. 
Analise a transcrição e sugira um produto da lista abaixo.

Responda ESTRITAMENTE em formato JSON.

LISTA DE PRODUTOS:
{json_produtos}

FORMATO DE RESPOSTA (JSON):
{{
  "pensamentos": "Faça uma análise breve dos sintomas citados e compare com a lista de produtos antes de decidir.",
  "sugestao": "Nome do Produto" (ou null se nenhum for adequado),
  "explicacao": "Explicação técnica e direta sobre o porquê da escolha."
}}
"""

# Prompt Free (Aberto, com travas de segurança)
SYSTEM_PROMPT_TEMPLATE_FREE = """
Você é um assistente sênior de farmácia. 
Analise a transcrição e sugira o produto mais adequado disponível no mercado brasileiro.

REGRAS DE SEGURANÇA (CRÍTICO):
1. NUNCA sugira medicamentos que exijam RETENÇÃO DE RECEITA (ex: antibióticos, tarja preta, controlados).
2. Priorize Medicamentos Isentos de Prescrição (MIPs), suplementos e dermocosméticos.
3. Se identificar gravidade ou necessidade de receita, sugira encaminhamento médico.

Responda ESTRITAMENTE em formato JSON.

FORMATO DE RESPOSTA (JSON):
{{
  "pensamentos": "Faça uma análise breve dos sintomas e verifique se o produto é controlado ou requer receita retida.",
  "sugestao": "Nome Comercial do Produto" (ou null se nenhum for seguro/adequado),
  "explicacao": "Explicação técnica e direta sobre o porquê da escolha e modo de uso resumido."
}}
"""

# Função limpa: removemos o argumento 'nome_funcionario'
def analisar_texto(texto: str) -> str | None:
    if not client:
        return None
        
    try:
        # Define qual prompt usar
        if RESTRICT_PRODUCTS and BASE_DE_PRODUTOS:
            produtos_str = json.dumps(BASE_DE_PRODUTOS, ensure_ascii=False)
            prompt = SYSTEM_PROMPT_TEMPLATE_STRICT.format(json_produtos=produtos_str)
        else:
            # Modo Livre (ou fallback se lista vazia)
            prompt = SYSTEM_PROMPT_TEMPLATE_FREE

        response = client.chat.completions.create(
            model="grok-3-mini",  # Mantido o modelo solicitado
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