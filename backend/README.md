
# Smart Library Monitoring

## Sistema de Monitoramento Ambiental de Bibliotecas

Projeto Integrador II — Ciências de Dados | SENAI | 2026

## 1. Sobre o projeto

O Smart Library Monitoring é um sistema de monitoramento ambiental desenvolvido para acompanhar as condições de uma biblioteca por meio de sensores IoT.

O projeto busca identificar condições ambientais inadequadas que possam comprometer a conservação do acervo, o conforto dos usuários e a qualidade do ambiente.

Os dados coletados são transmitidos pelo protocolo MQTT, processados em Python e armazenados em um banco de dados MySQL.

Quando uma medição ultrapassa os limites estabelecidos, o sistema registra uma ocorrência e envia automaticamente uma notificação por e-mail.

## 2. Objetivos

- Monitorar as condições ambientais da biblioteca.
- Automatizar a coleta e o armazenamento das medições.
- Identificar indicadores fora dos limites estabelecidos.
- Enviar alertas automáticos por e-mail.
- Disponibilizar informações por meio de uma API REST.
- Permitir análises históricas dos dados coletados.
- Auxiliar na tomada de decisões baseada em dados.

## 3. Tecnologias utilizadas

| Tecnologia | Finalidade |
|---|---|
| Python | Desenvolvimento do backend |
| Flask | Desenvolvimento da API REST |
| SQLAlchemy | Integração com o banco de dados |
| MySQL | Armazenamento dos dados |
| MQTT | Comunicação com dispositivos IoT |
| Paho MQTT | Recebimento das mensagens |
| Gmail API | Envio automático de notificações |
| OAuth 2.0 | Autorização de acesso à Gmail API |
| SQLite | Ambiente de testes automatizados |
| Git | Controle de versões |
| GitHub | Versionamento e colaboração |
| Figma | Prototipação do dashboard |

## 4. Indicadores monitorados

| Indicador | Campo |
|---|---|
| Temperatura | temperature |
| Umidade relativa do ar | humidity |
| Dióxido de carbono | CO2 |
| Material particulado 1 | particula1 |
| Material particulado 2 | particula2 |

O sistema utiliza cinco indicadores ambientais.

Pressão atmosférica e altitude não fazem parte do escopo atual do projeto.

## 5. Arquitetura do sistema

```mermaid
flowchart TD
    A[Sensor IoT] --> B[Broker MQTT]
    B --> C[Backend Python]
    C --> D[Validacao dos dados]
    D --> E[(MySQL)]
    E --> F[Verificacao dos limites]
    F --> G[Gerenciamento de ocorrencias]
    G --> H[Notificacoes]
    H --> I[Gmail API]
    I --> J[Email do responsavel]
    E --> K[API REST Flask]
    K --> L[Dashboard - etapa futura]
```

## 6. Estrutura do projeto

```text
biblioteca-monitoramento-ambiental/
|
|-- backend/
|   |-- mqtt.py
|   |-- alertas.py
|   |-- alerta_email.py
|   |-- rotas_alertas.py
|   |-- erros.py
|   |-- testar_banco.py
|   |-- teste_email.py
|   |-- teste_integracao.py
|   |-- simular_sensor.py
|   |-- requirements.txt
|   |-- .gitignore
|
|-- database/
|
|-- .gitignore
|-- README.md
```

Os arquivos de configuração e credenciais são mantidos localmente e não devem ser compartilhados no GitHub.

## 7. Banco de dados

O sistema utiliza um banco de dados relacional MySQL denominado monitoramento_bd.

### Principais tabelas

| Tabela | Responsabilidade |
|---|---|
| ambiente | Ambientes monitorados |
| sensor | Dispositivos IoT cadastrados |
| indicador | Indicadores ambientais |
| limite | Limites de monitoramento |
| medicao | Histórico das medições |
| ocorrencia | Registro dos alertas |
| notificacao | Histórico de envio dos e-mails |

### Relacionamentos

- Um ambiente pode possuir vários sensores.
- Um sensor pode registrar várias medições.
- Um ambiente pode possuir diferentes limites ambientais.
- Uma medição pode gerar ocorrências.
- Uma ocorrência pode possuir notificações.

### Atualização de um banco existente

Caso a tabela notificacao ainda não possua o controle de tentativas, execute no MySQL Workbench:

```sql
USE monitoramento_bd;

ALTER TABLE notificacao
ADD COLUMN tentativas INT NOT NULL DEFAULT 0,
ADD COLUMN proxima_tentativa DATETIME NULL,
ADD COLUMN ultimo_erro VARCHAR(500) NULL;
```

Execute somente se essas colunas ainda não existirem.

As alterações devem ser realizadas diretamente no banco existente, sem excluir ou recriar tabelas.

## 8. Instalação

### Pré-requisitos

- Python instalado.
- MySQL Server.
- MySQL Workbench.
- Git.
- Acesso a um broker MQTT.
- Credenciais autorizadas da Gmail API.

### Clonar o repositório

```bash
git clone https://github.com/borgessx/biblioteca-monitoramento-ambiental.git
```

### Acessar o projeto

```bash
cd biblioteca-monitoramento-ambiental
cd backend
```

### Criar um ambiente virtual

```bash
python -m venv .venv
```

### Ativar o ambiente virtual no Windows

```cmd
.venv\Scripts\activate
```

### Instalar as dependências

```bash
python -m pip install -r requirements.txt
```

## 9. Configuração do ambiente

O backend utiliza variáveis de ambiente para configurar a comunicação com o banco de dados, broker MQTT e destinatário das notificações.

As configurações devem ser realizadas no arquivo .env, utilizando os nomes de variáveis definidos no código do backend.

Exemplos de parâmetros utilizados:

```env
DATABASE_URL=mysql+pymysql://usuario:senha@127.0.0.1:3306/monitoramento_bd

MQTT_BROKER=test.mosquitto.org
MQTT_PORT=1883
MQTT_TOPIC=seu_topico_mqtt

EMAIL_DESTINATARIO=seu_email@exemplo.com
```

Utilize as configurações reais do ambiente de execução.

Não compartilhe senhas ou credenciais no repositório.

## 10. Comunicação MQTT

O backend recebe mensagens JSON publicadas pelos dispositivos IoT.

Exemplo de mensagem:

```json
{
    "temperature": 22.5,
    "humidity": 50.0,
    "CO2": 650,
    "particula1": 12.3,
    "particula2": 8.7,
    "timestamp": 1795125763
}
```

Após receber uma mensagem, o sistema:

1. Valida o formato JSON.
2. Identifica o sensor.
3. Valida os valores recebidos.
4. Converte o timestamp.
5. Armazena a medição.
6. Verifica os limites ambientais.
7. Registra ocorrências quando necessário.

## 11. Gerenciamento de ocorrências

O sistema identifica automaticamente medições que ultrapassam os limites cadastrados.

### Status das ocorrências

- ABERTA: condição ambiental inadequada.
- ENCERRADA: condição ambiental normalizada.

Enquanto uma ocorrência permanecer aberta, novas medições fora do mesmo limite não devem gerar ocorrências repetidas para aquele sensor e limite.

Quando o indicador retornar às condições adequadas, a ocorrência será encerrada automaticamente.

Caso o problema volte a acontecer, uma nova ocorrência poderá ser registrada.

## 12. Integração Gmail API

O sistema utiliza a Gmail API para enviar notificações aos responsáveis pelo ambiente monitorado.

A autorização é realizada por meio do protocolo OAuth 2.0.

Arquivos utilizados:

- credentials.json
- token.json

Esses arquivos devem permanecer exclusivamente no ambiente local.

### Status das notificações

| Status | Descrição |
|---|---|
| PENDENTE | Aguardando envio |
| ENVIANDO | Envio em processamento |
| ENVIADO | Envio realizado |
| ERRO | Falha definitiva no envio |

### Controle de tentativas

O sistema foi implementado para realizar até três tentativas de envio.

- Primeira tentativa: envio imediato.
- Segunda tentativa: após 60 segundos da primeira falha.
- Terceira tentativa: após 120 segundos da segunda falha.
- Após três falhas: notificação marcada como ERRO.

A funcionalidade reutiliza o mesmo registro de notificação.

## 13. API REST

A API é desenvolvida com Flask e disponibiliza os dados armazenados no MySQL.

Endereço local:

http://127.0.0.1:8080

### Sistema

| Método | Endpoint | Descrição |
|---|---|---|
| GET | /health | Verificar disponibilidade |
| GET | /api/mqtt/status | Status da comunicação MQTT |

### Medições

| Método | Endpoint | Descrição |
|---|---|---|
| GET | /api/leituras | Consultar medições |
| GET | /api/leituras/ultima | Última medição |
| GET | /api/leituras/{id} | Medição específica |
| GET | /api/historico/{variavel} | Histórico do indicador |

### Sensores

| Método | Endpoint | Descrição |
|---|---|---|
| GET | /api/sensores | Sensores cadastrados |
| GET | /api/sensores/{codigo}/leituras | Medições do sensor |

### Ocorrências

| Método | Endpoint | Descrição |
|---|---|---|
| GET | /api/ocorrencias | Histórico de ocorrências |
| GET | /api/ocorrencias/abertas | Ocorrências ativas |
| GET | /api/ocorrencias/encerradas | Ocorrências resolvidas |

### Notificações e indicadores

| Método | Endpoint | Descrição |
|---|---|---|
| GET | /api/notificacoes | Histórico de notificações |
| GET | /api/indicadores | Indicadores monitorados |
| GET | /api/limites | Limites ambientais |
| GET | /api/ambientes | Ambientes cadastrados |
| GET | /api/kpis | Indicadores gerais do sistema |

### Exportação

| Método | Endpoint | Descrição |
|---|---|---|
| GET | /api/exportar/medicoes | Exportação CSV de medições |
| GET | /api/exportar/ocorrencias | Exportação CSV de ocorrências |

## 14. Filtros da API

Exemplos de consultas:

### Filtrar medições por sensor

```text
/api/leituras?sensor=IOT_PADRAO
```

### Filtrar medições por período

```text
/api/leituras?inicio=2026-11-01&fim=2026-11-20
```

### Consultar histórico de temperatura

```text
/api/historico/temperature
```

### Consultar ocorrências abertas

```text
/api/ocorrencias?status=ABERTA
```

### Consultar ocorrências de temperatura

```text
/api/ocorrencias?indicador=temperature
```

### Consultar notificações enviadas

```text
/api/notificacoes?status=ENVIADO
```

### Exportar as últimas 100 medições

```text
/api/exportar/medicoes?limite=100
```

Os parâmetros disponíveis variam conforme o endpoint.

## 15. Indicadores de desempenho

O endpoint /api/kpis disponibiliza:

- Total de medições.
- Total de sensores.
- Total de ambientes.
- Total de ocorrências.
- Ocorrências abertas.
- Ocorrências encerradas.
- E-mails enviados.
- E-mails pendentes.
- E-mails em processamento.
- E-mails com falha.

Essas informações serão utilizadas no dashboard.

## 16. Tratamento de erros

A API possui tratamento centralizado de exceções.

| Código HTTP | Descrição |
|---|---|
| 200 | Operação realizada com sucesso |
| 400 | Requisição inválida |
| 404 | Recurso não encontrado |
| 405 | Método não permitido |
| 500 | Erro interno do servidor |

Exemplo de resposta:

```json
{
    "status": 400,
    "erro": "Valor invalido",
    "mensagem": "Status de ocorrência inválido."
}
```

## 17. Executar o sistema

Na pasta backend, com o ambiente virtual ativado:

```bash
python mqtt.py
```

Acessar a API:

http://127.0.0.1:8080/health

### Simular medições

Em outro terminal:

```bash
python simular_sensor.py
```

Utilize um ambiente e tópico destinados a testes.

## 18. Testes de integração

Para executar os testes automatizados:

```bash
python teste_integracao.py
```

Os testes abrangem:

- Validação das mensagens.
- Armazenamento das medições.
- Controle de duplicidades.
- Tratamento de mensagens inválidas.
- Conversão de timestamps.
- Funcionamento dos endpoints.
- Gerenciamento de ocorrências.
- Envio simulado de notificações.
- Tratamento de falhas de envio.

Durante o desenvolvimento, uma execução registrou 11 testes aprovados.

A suíte adicional de testes da API foi adiada.

## 19. Segurança

O projeto utiliza .gitignore para proteger arquivos confidenciais.

Arquivos que não devem ser versionados:

- .env
- credentials.json
- token.json
- client_secret_*.json
- .venv/
- __pycache__/
- Arquivos de logs e dados temporários.

A API destina-se atualmente ao ambiente acadêmico local e não possui autenticação completa para acesso público.

O broker MQTT público deve ser utilizado apenas para testes, sem transmissão de informações confidenciais.

Credenciais anteriormente expostas no histórico do Git devem ser renovadas.

## 20. Limitações conhecidas

- A implementação do dashboard ainda está pendente.
- A validação automatizada adicional da API foi adiada.
- Os limites ambientais devem ser adequados ao ambiente real.
- Notificações interrompidas durante o envio podem permanecer com status ENVIANDO.
- Falhas de comunicação podem ocasionar reenvios duplicados.
- O servidor Flask atual destina-se ao desenvolvimento.
- A integração Gmail depende da validade da autorização OAuth.

## 21. Status do projeto

- [x] Planejamento
- [x] Modelagem do banco de dados
- [x] Comunicação MQTT
- [x] Armazenamento das medições
- [x] API REST
- [x] Alertas automáticos
- [x] Integração Gmail API
- [x] Gerenciamento de ocorrências
- [x] Controle de tentativas
- [x] Exportação CSV
- [x] Documentação do backend
- [ ] Prototipação do dashboard no Figma
- [ ] Implementação do dashboard
- [ ] Integração final do frontend
- [ ] Validação completa do sistema

## 22. Próximas etapas

O projeto continuará com o desenvolvimento do protótipo visual no Figma.

Após a aprovação do design, o dashboard será implementado e integrado à API REST.

A interface permitirá acompanhar as condições ambientais, consultar históricos, visualizar indicadores e acompanhar ocorrências.

---

Projeto Integrador II

Ciências de Dados — SENAI

Smart Library Monitoring | 2026
