🤖 Balto Server Backend

Serviço de backend em Python (WebSockets + HTTP) responsável por toda a pipeline de análise de áudio em tempo real do sistema Balto, que inclui: Detecção de Atividade de Voz (VAD), Transcrição e Análise de IA para sugestões de produtos em farmácias.

⚙️ Pré-requisitos

Para executar o servidor Balto, é essencial ter:

Docker

Docker Compose

Git

🔑 Configuração (Variáveis de Ambiente)

O servidor depende de variáveis de ambiente para inicialização e acesso às APIs de terceiros. Estas devem ser configuradas no arquivo .env na raiz do projeto server/.

Variável

Uso

Descrição

OPENAI_API_KEY

🧠 Análise (Grok)

Chave da API para o modelo Grok-mini (via xAI).

ELEVENLABS_API_KEY

🎤 Transcrição

Chave da API para o serviço de Speech-to-Text.

DB_FILE

💾 Banco de Dados

Caminho local do arquivo SQLite (./dados/registro_vendas.db).

PORT

🌐 Servidor

Porta para a comunicação HTTP e WebSocket (Padrão: 8765).

🚀 Executando o Servidor com Docker Compose

Siga estes passos para colocar o servidor no ar de forma isolada e fácil:

1. Iniciar (Build e Run)

Este comando constrói a imagem Docker, cria o volume para o banco de dados (balto-dados) e inicia o contêiner em segundo plano (-d).

docker-compose up -d --build


2. Monitorar os Logs

Para diagnosticar ou acompanhar o funcionamento da pipeline:

docker-compose logs -f


3. Parar o Serviço

Para encerrar e remover o contêiner (mas manter o volume de dados):

docker-compose down


📡 Referência da API

O servidor utiliza portas distintas para operações de cadastro (HTTP) e comunicação em tempo real (WebSocket).

A. Endpoints HTTP (Cadastro)

POST /cadastro/cliente

Cria um registro para o cliente (e.g., a rede de farmácias).

Payload de Exemplo

{
  "email": "contato@redepharma.com",
  "razao_social": "Rede Pharma LTDA",
  "telefone": "11999998888"
}


Resposta de Sucesso (201 Created)

{
  "codigo": "123456"
}


POST /cadastro/balcao

Cria um ponto de venda (balcão) e gera a chave de autenticação (API Key).

Payload de Exemplo

{
  "nome_balcao": "Loja 01 - Centro",
  "user_codigo": "123456" 
}


Resposta de Sucesso (201 Created)

{
  "api_key": "a1b2c3d4-e5f6-7890-abcd-1234567890ef"
}


B. Protocolo WebSocket

Endpoint: wss://[seu-domino]:8765/ws

O cliente front-end deve seguir rigorosamente o seguinte protocolo:

Passo

Direção

Comando

Detalhes

1

➡️ Cliente -> Servidor

auth

Enviar imediatamente a API Key no formato JSON.

2

➡️ Cliente -> Servidor

Binary Data

Envio contínuo de chunks de áudio (16kHz, 16-bit PCM).

3

⬅️ Servidor -> Cliente

recomendar

Mensagem de IA com uma sugestão de produto e id_interacao.

4

➡️ Cliente -> Servidor

feedback

Reportar o resultado da interação (venda_realizada ou venda_perdida).

Exemplo de Recomendação (Passo 3):

{
  "comando": "recomendar",
  "mensagem": "Sugerir Gelol",
  "id_interacao": "b1c2d3e4-..."
}


🧪 Teste Ponta-a-Ponta

Para garantir que o servidor está operando corretamente, utilize o script de teste automatizado (auto_test.py no seu repositório de testes).

Instale as dependências de teste:

pip install requests websockets


Aponte a URL: Configure a variável BASE_URL no script auto_test.py para a URL do seu servidor.

Execute:

python auto_test.py
