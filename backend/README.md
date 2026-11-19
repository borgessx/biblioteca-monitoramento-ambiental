# Smart Library Monitoring 📚🌡️

### Sistema de Monitoramento Ambiental Inteligente para Bibliotecas

Projeto Integrador II — **Ciência de Dados | SENAI**

## 📌 Sobre o projeto

O **Smart Library Monitoring** é um projeto acadêmico que propõe acompanhar as condições ambientais de bibliotecas por meio de sensores e séries temporais, permitindo visualizar medições e identificar condições que possam prejudicar a conservação de livros, documentos e dispositivos eletrônicos.

A solução prevê **monitoramento em tempo real**, **registro automático de ocorrências** e **alertas por e-mail** quando os indicadores ultrapassarem limites configurados.

## ❗ Problema identificado

A ausência de um monitoramento ambiental contínuo dificulta a análise do histórico de temperatura, umidade e qualidade do ar. Sem registros organizados e alertas, condições inadequadas podem passar despercebidas, aumentando o risco de danos ao acervo e de custos de reposição.

## 🎯 Objetivos

- Aumentar a vida útil de livros, documentos e dispositivos eletrônicos.
- Registrar e consultar séries temporais das condições ambientais.
- Identificar o **sensor** e o **ambiente** de origem de cada medição.
- Exibir indicadores em um dashboard.
- Automatizar o registro de ocorrências e o envio de alertas.
- Reduzir desperdícios e contribuir para a sustentabilidade universitária.

## 📊 Indicadores monitorados

| Campo no banco | Indicador | Unidade |
| --- | --- | --- |
| `temperature` | Temperatura | °C |
| `pressure` | Pressão atmosférica | hPa |
| `altitude` | Altitude | m |
| `humidity` | Umidade relativa | % |
| `CO2` | Concentração de CO₂ | ppm |
| `particula1` | Primeira medição de partículas | Conforme sensor |
| `particula2` | Segunda medição de partículas | Conforme sensor |
| `registro_tempo` | Data e hora da medição | Data/hora |

> As unidades e a interpretação de `particula1` e `particula2` serão confirmadas conforme os sensores adotados.

## 🗃️ Banco de dados

O modelo relacional foi projetado para **MySQL** e inclui sete tabelas:

| Tabela | Finalidade |
| --- | --- |
| `ambiente` | Locais acompanhados |
| `sensor` | Dispositivos associados a cada ambiente |
| `medicao` | Valores coletados e seus horários |
| `indicador` | Tipos de indicadores e respectivas unidades |
| `limite` | Valores mínimos e máximos por ambiente e indicador |
| `ocorrencia` | Registro de condições fora dos limites |
| `notificacao` | Histórico de tentativas e envios de alertas |

**Relacionamentos principais:**

```text
AMBIENTE ──< SENSOR ──< MEDICAO ──< OCORRENCIA ──< NOTIFICACAO
    │                                   │
    └──< LIMITE >── INDICADOR           └──── LIMITE
```

A tabela `medicao` mantém os campos obrigatórios do projeto: `id`, `temperature`, `pressure`, `altitude`, `humidity`, `CO2`, `particula1`, `particula2` e `registro_tempo`, além de `id_sensor` para identificar a origem da coleta.

## 🛠️ Tecnologias

**Banco de dados:** MySQL e MySQL Workbench.

**Tecnologias planejadas para a aplicação:** Python, Flask (API), Pandas (análise temporal), Streamlit (dashboard) e uma API de e-mail para os alertas.

A integração com sensores IoT depende dos dispositivos definidos pelo grupo.

## 🔄 Funcionamento previsto

1. Os sensores coletam as condições ambientais.
2. A aplicação recebe e armazena as medições com data, hora e identificação do sensor.
3. Os dados são consultados e visualizados em gráficos de séries temporais.
4. A aplicação compara as medições com os limites cadastrados para cada ambiente.
5. Quando necessário, registra uma ocorrência e envia um alerta por e-mail.
6. O histórico de ocorrências e notificações permanece disponível para consulta.

## 🚀 Como criar o banco de dados

**Pré-requisitos:** MySQL Server e MySQL Workbench instalados.

1. Clone o repositório:
   ```bash
   git clone https://github.com/SEU-USUARIO/smart-library-monitoring.git
   ```
2. Abra o MySQL Workbench e conecte-se ao servidor MySQL.
3. Abra o arquivo SQL do projeto (por exemplo, `database/ddl.sql`).
4. Execute o script para criar o banco `monitoramento_biblioteca` e suas tabelas.
5. Confirme a criação:
   ```sql
   USE monitoramento_biblioteca;
   SHOW TABLES;
   ```

> Substitua `SEU-USUARIO` pelo usuário real do GitHub e ajuste o caminho do arquivo SQL conforme a organização do repositório. **Atenção:** se o script incluir `DROP DATABASE IF EXISTS`, a execução apagará os dados existentes desse banco.

## 🗂️ Organização sugerida

```text
smart-library-monitoring/
├── database/
│   └── ddl.sql
├── api/                 # Planejado
├── dashboard/           # Planejado
└── README.md
```

## ✅ Etapas do projeto

- [x] Definição do problema e dos objetivos
- [x] Levantamento dos indicadores ambientais
- [x] Modelagem do DER
- [x] Elaboração do DDL
- [ ] Integração dos sensores e persistência das medições
- [ ] Desenvolvimento da API
- [ ] Dashboard com séries temporais
- [ ] Regras para registro automático de ocorrências
- [ ] Envio de alertas por e-mail
- [ ] Testes e documentação final

> O checklist registra a elaboração do modelo e do código SQL, não a validação da execução do banco ou a implantação da aplicação.

## 🌱 Impacto esperado

Contribuir para a **conservação preventiva do acervo**, a redução de desperdícios e custos de reposição e a melhoria da tomada de decisões por meio de dados ambientais históricos e em tempo real.

---

**Projeto acadêmico — Projeto Integrador II | SENAI**
