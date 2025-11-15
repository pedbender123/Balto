Servidor Balto - BackendServiço de backend em Python (WebSocket + HTTP) para a pipeline de análise de áudio Balto.1. Pré-requisitosDockerDocker ComposeGit2.

# Configurações do Servidor
PORT=8765
DB_FILE=./dados/registro.db
3. Executando (Docker)Com o Docker e o Docker Compose instalados, execute:# Constrói e inicia o contêiner em modo 'detached' (background)
docker-compose up -d --build
Para ver os logs do servidor:docker-compose logs -f
Para parar o servidor:docker-compose down
4. Referência da APIO servidor expõe endpoints HTTP e WebSocket na porta definida (ex: 8765).Endpoints HTTP (para Cadastro)POST /cadastro/clienteRegistra uma nova entidade "Cliente" (ex: rede de farmácias).Request Body:{
  "email": "contato@redepharma.com",
  "razao_social": "Rede Pharma LTDA",
  "telefone": "11999998888"
}
Response (201/CREATED):{
  "codigo": "123456"
}
Response (409/CONFLICT):{
  "error": "Email ou código já existe..."
}
POST /cadastro/balcaoRegistra um "Balcão" (ponto de venda) vinculado a um Cliente.Request Body:{
  "nome_balcao": "Loja 01 - Centro",
  "user_codigo": "123456"
}
Response (201/CREATED):{
  "api_key": "a1b2c3d4-e5f6-7890-abcd-1234567890ef"
}
Response (400/BAD REQUEST):{
  "error": "Código de usuário inválido"
}
Protocolo WebSocketEndpoint: wss://[seu-domino]/wsO cliente deve seguir este fluxo:1. Conexão e Autenticação (Cliente -> Servidor)Imediatamente após a conexão ser estabelecida, o cliente DEVE enviar:{
  "comando": "auth",
  "api_key": "a1b2c3d4-e5f6-7890-abcd-1234567890ef"
}
Se esta mensagem não for enviada ou a api_key for inválida, o servidor encerrará a conexão.2. Stream de Áudio (Cliente -> Servidor)O cliente envia bytes de áudio (formato esperado: 16kHz, 16-bit PCM, mono).3. Recomendação (Servidor -> Cliente)Quando uma oportunidade é detectada, o servidor envia:{
  "comando": "recomendar",
  "mensagem": "Sugerir Dorflex",
  "id_interacao": "b1c2d3e4-..."
}
4. Feedback (Cliente -> Servidor)Após a interação, o cliente DEVE reportar o resultado:{
  "comando": "feedback",
  "id_interacao": "b1c2d3e4-...",
  "resultado": "venda_realizada" 
}
Resultados válidos: venda_realizada ou venda_perdida.5. TestandoPara testar a API ponta-a-ponta, use o script auto_test.py (localizado no repositório de testes).Navegue até a pasta do script de teste.Crie um ambiente virtual (recomendado):python3 -m venv venv
source venv/bin/activate
Instale as dependências de teste:pip install requests websockets
Edite a BASE_URL no script auto_test.py para apontar para seu servidor.Execute o teste:python auto_test.py
