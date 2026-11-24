
/*
  BIOPRESERVE FÁCIL — SENAI

  MODO FRONTEND INDEPENDENTE

  - Open-Meteo com dados externos reais/modelados
  - Integração interna opcional com backend Flask
  - Gráfico único com quatro curvas
  - Temperatura em °C e umidade em %
  - Intervalo de 1 hora
  - Sem dados fictícios
*/

const $ = id => document.getElementById(id);

const HORA = 3600000;
const FUSO = "America/Sao_Paulo";

let grafico = null;
let periodoDias = 1;
let leituras = [];
let limites = {};
let climaExterno = [];
let backendDisponivel = false;
let sequenciaGrafico = 0;

const INDICADORES = [
  "temperature",
  "humidity",
  "CO2",
  "particula1",
  "particula2"
];

function valorNumerico(valor) {
  if (
    valor === null ||
    valor === undefined ||
    valor === ""
  ) {
    return null;
  }

  const n = Number(valor);

  return Number.isFinite(n) ? n : null;
}

function numero(valor, casas = 1) {
  const n = valorNumerico(valor);

  return n === null
    ? "—"
    : n.toLocaleString("pt-BR", {
        minimumFractionDigits: casas,
        maximumFractionDigits: casas
      });
}

function dataDe(valor) {
  if (!valor) return null;

  if (typeof valor === "number") {
    const d = new Date(
      valor < 1e12 ? valor * 1000 : valor
    );

    return Number.isNaN(d.getTime())
      ? null
      : d;
  }

  const texto = String(valor);

  const local = texto.match(
    /^(\d{4})-(\d\d)-(\d\d)[ T](\d\d):(\d\d)(?::(\d\d))?$/
  );

  const data = local
    ? new Date(
        +local[1],
        +local[2] - 1,
        +local[3],
        +local[4],
        +local[5],
        +(local[6] || 0)
      )
    : new Date(texto);

  return Number.isNaN(data.getTime())
    ? null
    : data;
}

function dataLeitura(item) {
  return dataDe(
    item.registro_tempo ??
    item.timestamp ??
    item.data_hora ??
    item.data_registro ??
    item.data
  );
}

function horaCheia(data) {
  const d = new Date(data);
  d.setMinutes(0, 0, 0);
  return d.getTime();
}

function formatarHora(tempo) {
  return new Date(tempo).toLocaleTimeString(
    "pt-BR",
    {
      hour: "2-digit",
      minute: "2-digit"
    }
  );
}

function formatarData(tempo) {
  if (!tempo) return "—";

  const d = tempo instanceof Date
    ? tempo
    : new Date(tempo);

  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function arrayResposta(resposta, nome) {
  if (Array.isArray(resposta)) {
    return resposta;
  }

  for (const chave of [
    nome,
    "dados",
    "registros",
    "resultados",
    "medicoes",
    "leituras",
    "items"
  ]) {
    if (Array.isArray(resposta?.[chave])) {
      return resposta[chave];
    }
  }

  return [];
}

async function consultar(nome) {
  const resposta = await fetch(
    "/dados/" + nome,
    { cache: "no-store" }
  );

  if (!resposta.ok) {
    throw new Error(
      `${nome}: HTTP ${resposta.status}`
    );
  }

  return resposta.json();
}

function situacao(campo, valor) {
  const n = valorNumerico(valor);
  const lim = limites[campo];

  if (n === null || !lim) {
    return {
      texto: "Sem avaliação",
      classe: ""
    };
  }

  if (
    (lim.min !== null && n < lim.min) ||
    (lim.max !== null && n > lim.max)
  ) {
    return {
      texto: "Alerta",
      classe: "alerta"
    };
  }

  return {
    texto: "Adequado",
    classe: "ok"
  };
}

function statusTag(id, estado) {
  const elemento = $(id);
  if (!elemento) return;

  elemento.textContent = estado.texto;
  elemento.className = "tag " + estado.classe;
}

function limparCards() {
  $("temperatura").textContent = "—";
  $("umidade").textContent = "—";
  $("co2").textContent = "CO₂: —";
  $("particulas").textContent = "Partículas: —";
  $("qualidade-ar").textContent = "Sem dados IoT";

  $("faixa-umidade").textContent =
    "Aguardando dados internos";

  $("risco-ressecamento").textContent = "—";
  $("risco-mofo").textContent = "—";

  $("marcador-temperatura").style.display = "none";

  $("posicao-temperatura").textContent =
    "Sem medição interna";

  statusTag("status-temperatura", {
    texto: "Indisponível",
    classe: ""
  });

  statusTag("status-umidade", {
    texto: "Indisponível",
    classe: ""
  });

  statusTag("situacao-ar", {
    texto: "Indisponível",
    classe: ""
  });

  $("indice").textContent = "—";

  $("nivel-preservacao").textContent =
    "Sem dados internos";

  $("indice-detalhe").textContent =
    "Índice calculado somente com leituras IoT";

  $("gauge-marker").setAttribute(
    "visibility",
    "hidden"
  );

  $("mensagem-central").textContent =
    "Backend interno não conectado";

  $("status-central").style.borderColor =
    "#92400e";

  $("resumo-dia").textContent =
    "O banco MySQL está em outro computador. " +
    "O gráfico externo pode ser consultado " +
    "normalmente pela Open-Meteo.";

  $("ultima-atualizacao").textContent =
    "Aguardando sensor IoT";

  $("sensor-status").textContent =
    "IoT desconectado";

  $("sensor-status").className =
    "tag alerta";
}

function carregarLimites(dados) {
  const lista = arrayResposta(
    dados,
    "limites"
  );

  limites = {};

  for (const item of lista) {
    if (
      [false, 0, "0", "false"]
        .includes(item.ativo)
    ) {
      continue;
    }

    const campo =
      item.campo ?? item.indicador_campo;

    if (!INDICADORES.includes(campo)) {
      continue;
    }

    const min = valorNumerico(
      item.valor_minimo
    );

    const max = valorNumerico(
      item.valor_maximo
    );

    if (min === null && max === null) {
      continue;
    }

    limites[campo] = { min, max };
  }

  if (limites.humidity) {
    $("faixa-umidade").textContent =
      `Faixa operacional: ` +
      `${limites.humidity.min ?? "—"}% a ` +
      `${limites.humidity.max ?? "—"}%`;
  }
}

function pontuacaoIndicador(valor, limite) {
  const n = valorNumerico(valor);

  if (n === null || !limite) return null;

  const min = limite.min;
  const max = limite.max;

  if (min !== null && n < min) {
    const escala = max !== null
      ? Math.max(max - min, 1)
      : Math.max(Math.abs(min), 1);

    return Math.max(
      0,
      100 * (1 - (min - n) / escala)
    );
  }

  if (max !== null && n > max) {
    const escala = min !== null
      ? Math.max(max - min, 1)
      : Math.max(Math.abs(max), 1);

    return Math.max(
      0,
      100 * (1 - (n - max) / escala)
    );
  }

  return 100;
}

function atualizarIndice(dados) {
  const notas = INDICADORES
    .map(campo =>
      pontuacaoIndicador(
        dados[campo],
        limites[campo]
      )
    )
    .filter(n => n !== null);

  if (!notas.length) {
    $("indice").textContent = "—";
    return;
  }

  const media = notas.reduce(
    (soma, n) => soma + n,
    0
  ) / notas.length;

  $("indice").textContent =
    Math.round(media) + "%";

  $("nivel-preservacao").textContent =
    notas.length < 5
      ? `Índice parcial (${notas.length}/5)`
      : media >= 85
      ? "Condições favoráveis"
      : media >= 60
      ? "Atenção"
      : "Condições críticas";

  $("indice-detalhe").textContent =
    `Estimativa experimental • ${notas.length}/5 indicadores`;

  const angulo = Math.PI * (
    1 - media / 100
  );

  const marcador = $("gauge-marker");

  marcador.setAttribute(
    "cx",
    (90 + 69 * Math.cos(angulo)).toFixed(2)
  );

  marcador.setAttribute(
    "cy",
    (96 - 69 * Math.sin(angulo)).toFixed(2)
  );

  marcador.setAttribute(
    "visibility",
    "visible"
  );
}

function preencherCards(dados, kpis) {
  const temp = valorNumerico(
    dados.temperature
  );

  const umid = valorNumerico(
    dados.humidity
  );

  $("temperatura").textContent =
    numero(temp) + "°C";

  $("umidade").textContent =
    numero(umid, 0) + "%";

  const statusTemp = situacao(
    "temperature",
    temp
  );

  statusTag(
    "status-temperatura",
    statusTemp.texto === "Alerta"
      ? statusTemp
      : temp === null
      ? {
          texto: "Sem leitura",
          classe: ""
        }
      : temp >= 18 && temp <= 22
      ? {
          texto: "Agradável",
          classe: "ok"
        }
      : {
          texto: "Fora do ideal",
          classe: "alerta"
        }
  );

  statusTag(
    "status-umidade",
    situacao("humidity", umid)
  );

  if (temp !== null) {
    const marcador = $(
      "marcador-temperatura"
    );

    marcador.style.left =
      Math.max(
        0,
        Math.min(
          100,
          (temp - 15) / 11 * 100
        )
      ) + "%";

    marcador.style.display = "block";

    $("posicao-temperatura").textContent =
      `▲ Você está aqui (${numero(temp)}°)`;
  }

  const limU = limites.humidity;

  $("risco-ressecamento").textContent =
    umid !== null &&
    limU &&
    limU.min !== null
      ? umid < limU.min
        ? "Atenção"
        : "Baixo"
      : "—";

  $("risco-mofo").textContent =
    umid !== null &&
    limU &&
    limU.max !== null
      ? umid > limU.max
        ? "Atenção"
        : "Baixo"
      : "—";

  $("co2").textContent =
    "CO₂: " + numero(dados.CO2, 0) + " ppm";

  $("particulas").textContent =
    `Partículas: ${numero(dados.particula1)} / ` +
    numero(dados.particula2);

  const estadoAr = situacao(
    "CO2",
    dados.CO2
  );

  $("qualidade-ar").textContent =
    estadoAr.texto === "Adequado"
      ? "Puro & Fresco"
      : estadoAr.texto === "Alerta"
      ? "Atenção ao Ar"
      : "Sem avaliação";

  statusTag("situacao-ar", estadoAr);

  atualizarIndice(dados);

  const abertas = valorNumerico(
    kpis?.ocorrencias_abertas
  );

  $("mensagem-central").textContent =
    abertas === null
      ? "Ocorrências indisponíveis"
      : `${abertas} ocorrência(s) aberta(s)`;

  $("resumo-dia").textContent =
    abertas === null
      ? "Sem resumo das ocorrências"
      : abertas === 0
      ? "Nenhuma ocorrência aberta no banco."
      : `${abertas} ocorrência(s) abertas no banco.`;

  const data = dataLeitura(dados);

  $("ultima-atualizacao").textContent =
    data
      ? "Leitura: " + formatarData(data)
      : "Sem horário da leitura";
}

function preencherTabela() {
  const tbody = $("tabela-leituras");
  tbody.replaceChildren();

  if (!leituras.length) {
    const linha = document.createElement("tr");
    const td = document.createElement("td");

    td.colSpan = 4;
    td.textContent =
      "Sem leituras internas disponíveis neste PC.";

    linha.appendChild(td);
    tbody.appendChild(linha);

    $("total-leituras").textContent =
      "0 leituras internas";
    return;
  }

  const fragmento = document.createDocumentFragment();

  for (const item of leituras) {
    const linha = document.createElement("tr");

    for (const texto of [
      formatarData(dataLeitura(item)),
      numero(item.temperature) + "°C",
      numero(item.humidity, 0) + "%"
    ]) {
      const td = document.createElement("td");
      td.textContent = texto;
      linha.appendChild(td);
    }

    const estadoT = situacao(
      "temperature",
      item.temperature
    );

    const estadoU = situacao(
      "humidity",
      item.humidity
    );

    const td = document.createElement("td");
    const tag = document.createElement("span");

    const alerta =
      estadoT.texto === "Alerta" ||
      estadoU.texto === "Alerta";

    const avaliavel =
      estadoT.texto !== "Sem avaliação" &&
      estadoU.texto !== "Sem avaliação";

    tag.textContent = !avaliavel
      ? "Sem avaliação"
      : alerta
      ? "Atenção"
      : "Adequado";

    tag.className =
      "tag " +
      (!avaliavel
        ? ""
        : alerta
        ? "alerta"
        : "ok");

    td.appendChild(tag);
    linha.appendChild(td);
    fragmento.appendChild(linha);
  }

  tbody.appendChild(fragmento);

  $("total-leituras").textContent =
    `${leituras.length} leituras internas recebidas da API`;
}

// ========================================
// AGREGAÇÃO DAS LEITURAS INTERNAS
// ========================================

function mediasHorarias(itens) {
  const mapa = new Map();

  for (const item of itens) {
    const data = dataLeitura(item);

    if (!data) continue;

    const hora = horaCheia(data);

    if (!mapa.has(hora)) {
      mapa.set(hora, {
        x: hora,
        somaT: 0,
        qtdT: 0,
        somaU: 0,
        qtdU: 0
      });
    }

    const grupo = mapa.get(hora);
    const t = valorNumerico(item.temperature);
    const u = valorNumerico(item.humidity);

    if (t !== null) {
      grupo.somaT += t;
      grupo.qtdT++;
    }

    if (u !== null) {
      grupo.somaU += u;
      grupo.qtdU++;
    }
  }

  return [...mapa.values()]
    .sort((a, b) => a.x - b.x)
    .map(item => ({
      x: item.x,
      temperatura: item.qtdT
        ? item.somaT / item.qtdT
        : null,
      umidade: item.qtdU
        ? item.somaU / item.qtdU
        : null,
      qtdT: item.qtdT,
      qtdU: item.qtdU
    }));
}

// ========================================
// FAIXA DE CONFORTO DO FIGMA
// ========================================

const faixaConforto = {
  id: "faixaConforto",

  beforeDatasetsDraw(chart) {
    const escala = chart.scales.temp;
    const area = chart.chartArea;

    if (!escala || !area) return;

    const limitar = y => Math.max(
      area.top,
      Math.min(area.bottom, y)
    );

    const y22 = limitar(
      escala.getPixelForValue(22)
    );

    const y18 = limitar(
      escala.getPixelForValue(18)
    );

    const ctx = chart.ctx;

    ctx.save();

    ctx.fillStyle =
      "rgba(52,211,153,.10)";

    ctx.fillRect(
      area.left,
      y22,
      area.right - area.left,
      Math.max(0, y18 - y22)
    );

    ctx.strokeStyle =
      "rgba(52,211,153,.35)";

    ctx.setLineDash([4, 4]);

    for (const y of [y22, y18]) {
      ctx.beginPath();
      ctx.moveTo(area.left, y);
      ctx.lineTo(area.right, y);
      ctx.stroke();
    }

    ctx.setLineDash([]);

    ctx.fillStyle = "#6ee7b7";
    ctx.font = "10px Arial";

    ctx.fillText(
      "Faixa ideal 18–22°C",
      area.left + 8,
      Math.min(area.bottom - 8, y22 + 14)
    );

    ctx.restore();
  }
};

// ========================================
// GRÁFICO
// ========================================

function criarCurva(nome, dados, cor, eixo, externa) {
  return {
    label: nome,
    data: dados,
    yAxisID: eixo,

    borderColor: cor,
    backgroundColor: cor,
    borderWidth: externa ? 2.5 : 3,
    borderDash: externa ? [7, 5] : [],

    pointRadius: contexto => {
      const total = contexto.dataset.data.length;
      return total <= 24 ? 3 : 1.5;
    },

    pointHoverRadius: 6,
    pointBackgroundColor: cor,
    pointBorderColor: "#0b1525",
    pointBorderWidth: 1,

    tension: .35,
    cubicInterpolationMode: "monotone",

    spanGaps: false,
    fill: false
  };
}

function mostrarMensagemGrafico(texto) {
  $("aviso-grafico").textContent = texto;
  $("aviso-grafico").style.display =
    texto ? "flex" : "none";
}

function atualizarLegendas() {
  const ligado = $("comparar-externo").checked;

  $("legenda-temp-externa").hidden = !ligado;
  $("legenda-umid-externa").hidden = !ligado;
}

function criarGrafico() {
  if (grafico) {
    grafico.destroy();
    grafico = null;
  }

  if (typeof Chart === "undefined") {
    mostrarMensagemGrafico(
      "Chart.js indisponível. Verifique a internet."
    );
    return;
  }

  const mostrarExterno =
    $("comparar-externo").checked;

  const metrica = $("metrica").value;

  const mostrarTemp = metrica !== "humidity";
  const mostrarUmid = metrica !== "temperature";

  const agora = new Date();

  const inicio = new Date(
    agora.getFullYear(),
    agora.getMonth(),
    agora.getDate() - periodoDias + 1
  ).getTime();

  const fim = agora.getTime();

  const internas = mediasHorarias(
    leituras.filter(item => {
      const data = dataLeitura(item);
      return data &&
        data.getTime() >= inicio &&
        data.getTime() <= fim;
    })
  );

  const externas = mostrarExterno
    ? climaExterno.filter(item => {
        const data = dataDe(item.horario);

        return data &&
          data.getTime() >= inicio &&
          data.getTime() <= fim;
      })
    : [];

  const datasets = [];

  if (mostrarTemp && internas.length) {
    datasets.push(
      criarCurva(
        "Temperatura interna (IoT)",
        internas.map(p => ({
          x: p.x,
          y: p.temperatura,
          quantidade: p.qtdT
        })),
        "#ff9500",
        "temp",
        false
      )
    );
  }

  if (mostrarUmid && internas.length) {
    datasets.push(
      criarCurva(
        "Umidade interna (IoT)",
        internas.map(p => ({
          x: p.x,
          y: p.umidade,
          quantidade: p.qtdU
        })),
        "#00d2ff",
        "umid",
        false
      )
    );
  }

  if (mostrarTemp && externas.length) {
    datasets.push(
      criarCurva(
        "Temperatura externa (Open-Meteo)",
        externas
          .filter(p => p.temperatura !== null)
          .map(p => ({
            x: horaCheia(
              dataDe(p.horario)
            ),
            y: valorNumerico(p.temperatura)
          })),
        "#fde047",
        "temp",
        true
      )
    );
  }

  if (mostrarUmid && externas.length) {
    datasets.push(
      criarCurva(
        "Umidade externa (Open-Meteo)",
        externas
          .filter(p => p.umidade !== null)
          .map(p => ({
            x: horaCheia(
              dataDe(p.horario)
            ),
            y: valorNumerico(p.umidade)
          })),
        "#34d399",
        "umid",
        true
      )
    );
  }

  const possuiDados = datasets.some(
    d => d.data.length > 0
  );

  atualizarLegendas();

  if (!possuiDados) {
    mostrarMensagemGrafico(
      mostrarExterno
        ? "Não há dados para o período selecionado."
        : "Sem leituras IoT. Ative o comparativo externo."
    );

    return;
  }

  mostrarMensagemGrafico("");

  const valoresTemp = datasets
    .filter(d => d.yAxisID === "temp")
    .flatMap(d => d.data)
    .map(p => p.y)
    .filter(Number.isFinite);

  const minimoTemp = valoresTemp.length
    ? Math.min(17, ...valoresTemp) - 1
    : 15;

  const maximoTemp = valoresTemp.length
    ? Math.max(26, ...valoresTemp) + 1
    : 27;

  const ctx = $("grafico").getContext("2d");

  grafico = new Chart(ctx, {
    type: "line",

    plugins: [faixaConforto],

    data: { datasets },

    options: {
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      normalized: true,

      animation: {
        duration: 500
      },

      interaction: {
        mode: "nearest",
        intersect: false
      },

      plugins: {
        legend: {
          display: false
        },

        tooltip: {
          backgroundColor: "#162032",
          borderColor: "#334155",
          borderWidth: 1,
          titleColor: "#ffffff",
          bodyColor: "#e2e8f0",
          padding: 12,

          callbacks: {
            title: itens => itens.length
              ? formatarData(
                  new Date(itens[0].parsed.x)
                )
              : "",

            label: item => {
              const unidade =
                item.dataset.yAxisID === "temp"
                  ? "°C"
                  : "%";

              const fonte =
                item.dataset.label.includes("IoT")
                  ? "Média de leituras internas"
                  : "Modelo meteorológico externo";

              return (
                item.dataset.label +
                ": " +
                numero(item.parsed.y) +
                unidade +
                " • " +
                fonte
              );
            }
          }
        }
      },

      scales: {
        x: {
          type: "linear",
          min: inicio,
          max: fim,

          grid: {
            color: "rgba(35,50,77,.42)"
          },

          border: {
            display: false
          },

          ticks: {
            stepSize: HORA,
            maxTicksLimit: 8,
            autoSkip: true,
            maxRotation: 0,
            color: "#94a3b8",

            callback: valor => {
              const d = new Date(valor);

              return periodoDias === 1
                ? formatarHora(valor)
                : d.toLocaleString(
                    "pt-BR",
                    {
                      day: "2-digit",
                      month: "2-digit",
                      hour: "2-digit"
                    }
                  ) + "h";
            }
          }
        },

        temp: {
          type: "linear",
          position: "left",
          display: mostrarTemp,

          suggestedMin: minimoTemp,
          suggestedMax: maximoTemp,

          grid: {
            color: "rgba(35,50,77,.42)"
          },

          border: {
            display: false
          },

          title: {
            display: mostrarTemp,
            text: "Temperatura (°C)",
            color: "#fbbf24"
          },

          ticks: {
            color: "#fbbf24",
            callback: valor =>
              valor + "°C"
          }
        },

        umid: {
          type: "linear",
          position: "right",
          display: mostrarUmid,

          min: 0,
          max: 100,

          grid: {
            drawOnChartArea: !mostrarTemp,
            color: "rgba(35,50,77,.42)"
          },

          border: {
            display: false
          },

          title: {
            display: mostrarUmid,
            text: "Umidade (%)",
            color: "#67e8f9"
          },

          ticks: {
            color: "#67e8f9",
            callback: valor =>
              valor + "%"
          }
        }
      }
    }
  });

  const totalInternas = internas.length;
  const totalExternas = externas.length;

  $("observacao-grafico").textContent =
    `${totalInternas} horas com leituras IoT • ` +
    `${totalExternas} horas com clima externo. ` +
    "Intervalo de 1 hora.";

  $("observacao-grafico").style.color =
    "#34d399";
}

// ========================================
// CONSULTA OPEN-METEO
// ========================================

async function atualizarClimaExterno() {
  const id = ++sequenciaGrafico;

  if (!$("comparar-externo").checked) {
    climaExterno = [];

    $("comparativo-status").textContent =
      "Comparativo externo desativado.";

    criarGrafico();
    return;
  }

  $("comparativo-status").textContent =
    "Consultando Open-Meteo em São Caetano do Sul...";

  try {
    const resposta = await fetch(
      `/dados/clima-externo?dias=${periodoDias}`,
      { cache: "no-store" }
    );

    if (!resposta.ok) {
      throw new Error(
        "Falha HTTP " + resposta.status
      );
    }

    const dados = await resposta.json();

    if (
      id !== sequenciaGrafico ||
      !$("comparar-externo").checked
    ) {
      return;
    }

    climaExterno = Array.isArray(dados.horas)
      ? dados.horas
      : [];

    $("comparativo-status").textContent =
      `${climaExterno.length} horários externos ` +
      "obtidos da Open-Meteo • São Caetano do Sul, SP.";

    criarGrafico();

  } catch (erro) {
    if (id !== sequenciaGrafico) return;

    console.error(
      "Erro ao consultar Open-Meteo:",
      erro
    );

    climaExterno = [];

    $("comparativo-status").textContent =
      "Não foi possível consultar a Open-Meteo.";

    criarGrafico();
  }
}

// ========================================
// CONSULTA BACKEND OPCIONAL
// ========================================

async function atualizarInterno() {
  try {
    const [ultima, historico, kpis, listaLimites] =
      await Promise.all([
        consultar("ultima"),
        consultar("leituras"),
        consultar("kpis"),
        consultar("limites")
      ]);

    backendDisponivel = true;

    carregarLimites(listaLimites);

    leituras = arrayResposta(
      historico,
      "leituras"
    )
      .filter(item => dataLeitura(item))
      .sort(
        (a, b) =>
          dataLeitura(b) -
          dataLeitura(a)
      );

    const dados =
      ultima?.leitura ??
      ultima?.ultima ??
      ultima?.medicao ??
      ultima;

    preencherCards(dados, kpis);

    $("sensor-status").textContent =
      "IoT conectado";

    $("sensor-status").className =
      "tag cyan";

  } catch (erro) {
    backendDisponivel = false;
    leituras = [];
    limites = {};

    limparCards();
  }

  preencherTabela();
  criarGrafico();
}

// ========================================
// EVENTOS
// ========================================

for (
  const botao of document.querySelectorAll(
    "[data-periodo]"
  )
) {
  botao.addEventListener(
    "click",
    async () => {
      periodoDias = Number(
        botao.dataset.periodo
      );

      for (
        const item of document.querySelectorAll(
          "[data-periodo]"
        )
      ) {
        item.classList.toggle(
          "ativo",
          item === botao
        );
      }

      if ($("comparar-externo").checked) {
        await atualizarClimaExterno();
      } else {
        criarGrafico();
      }
    }
  );
}

$("metrica").addEventListener(
  "change",
  criarGrafico
);

$("comparar-externo").addEventListener(
  "change",
  atualizarClimaExterno
);

$("atualizar").addEventListener(
  "click",
  async () => {
    await atualizarInterno();

    if ($("comparar-externo").checked) {
      await atualizarClimaExterno();
    }
  }
);

$("relatar-problema").addEventListener(
  "click",
  () => {
    alert(
      "O registro manual depende do backend."
    );
  }
);

// ========================================
// INICIALIZAÇÃO
// ========================================

async function iniciar() {
  const seletor = $("ambiente");

  seletor.replaceChildren();
  seletor.add(
    new Option("Biblioteca", "")
  );
  seletor.disabled = true;

  limparCards();
  preencherTabela();

  // Habilita visualização externa automaticamente
  // quando o backend local não estiver acessível.
  await atualizarInterno();

  if (!backendDisponivel) {
    $("comparar-externo").checked = true;
  }

  if ($("comparar-externo").checked) {
    await atualizarClimaExterno();
  } else {
    criarGrafico();
  }
}

iniciar();

// Reconsulta o IoT periodicamente.
// O clima externo tem atualização menos frequente.
setInterval(
  atualizarInterno,
  30000
);

setInterval(
  () => {
    if ($("comparar-externo").checked) {
      atualizarClimaExterno();
    }
  },
  600000
);
