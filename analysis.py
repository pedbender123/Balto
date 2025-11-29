import os
import json
from openai import OpenAI

# --- Carregar a base de dados (Mantido igual) ---
PRODUTOS_DB_PATH = "produtos.json"
try:
    with open(PRODUTOS_DB_PATH, 'r', encoding='utf-8') as f:
        BASE_DE_PRODUTOS = json.load(f)
    print(f"Base de produtos '{PRODUTOS_DB_PATH}' carregada com {len(BASE_DE_PRODUTOS)} itens.")
except FileNotFoundError:
    print(f"ERRO FATAL: Base de produtos '{PRODUTOS_DB_PATH}' não encontrada.")
    BASE_DE_PRODUTOS = []
except json.JSONDecodeError:
    print(f"ERRO FATAL: Falha ao decodificar '{PRODUTOS_DB_PATH}'. Verifique o JSON.")
    BASE_DE_PRODUTOS = []


# --- MUDANÇA: Inicializar o cliente para OpenAI (GPT) ---
try:
    # Removemos a base_url da xAI e trocamos a chave para a da OpenAI
    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY")
    )
except Exception as e:
    print(f"Erro ao inicializar cliente OpenAI: {e}. Verifique sua OPENAI_API_KEY.")
    client = None

# --- Prompt Engineering (Mantido igual, funciona bem com GPT) ---
SYSTEM_PROMPT_TEMPLATE = """
Você é um assistente de farmácia especialista. Sua única função é analisar a transcrição de um cliente e, se aplicável, sugerir UM ÚNICO produto da lista de produtos permitidos.

REGRAS OBRIGATÓRIAS:
1.  Analise a transcrição do cliente.
2.  Identifique sintomas (ex: "dor de cabeça", "azia", "diarreia", "dor muscular").
3.  Compare os sintomas com as "indicacao" da base de produtos JSON fornecida.
4.  Se encontrar um produto relevante que o balconista possa ter esquecido de oferecer, retorne APENAS o nome do produto.
5.  Se NENHUM produto da lista for relevante para os sintomas, não retorne NADA (retorne uma string vazia).
6.  Não sugira nada que esteja fora da lista.

BASE DE PRODUTOS PERMITIDOS (JSON):
{json_produtos}

Exemplo 1:
Transcrição: "Nossa, bati meu joelho na porta, tá doendo muito."
Sua Resposta: Gelol

Exemplo 2:
Transcrição: "Tô com uma queimação aqui no estômago, acho que foi o almoço."
Sua Resposta: Sal de Fruta Eno

Exemplo 3:
Transcrição: "Eu queria só essa caixa de Tylenol mesmo, obrigado."
Sua Resposta: (string vazia)
"""

def analisar_texto(texto: str) -> str | None:
    """
    Analisa o texto e identifica oportunidades de recomendação
    usando a base de produtos e o GPT-4o-mini.
    """
    if not client or not BASE_DE_PRODUTOS:
        return None
        
    try:
        # Converte a base de produtos para uma string JSON formatada
        produtos_json_str = json.dumps(BASE_DE_PRODUTOS, indent=2, ensure_ascii=False)
        
        # Preenche o template do prompt
        prompt_final = SYSTEM_PROMPT_TEMPLATE.format(json_produtos=produtos_json_str)

        response = client.chat.completions.create(
            model="gpt-4o-mini", # <-- MUDANÇA: Substituindo grok-3-mini por gpt-4o-mini
            messages=[
                {"role": "system", "content": prompt_final},
                {"role": "user", "content": texto}
            ],
            temperature=0.0, # Baixa temperatura para respostas diretas
            max_tokens=50
        )
        
        recomendacao = response.choices[0].message.content.strip()
        
        # Se o modelo retornar vazio ou "nada", consideramos None
        if not recomendacao or recomendacao.lower() == "nada":
            return None
            
        # O prompt pede para sugerir SÓ o nome, então prefixamos a ação
        return f"Sugerir {recomendacao}"

    except Exception as e:
        print(f"Erro na API de Análise (OpenAI): {e}")
        return None