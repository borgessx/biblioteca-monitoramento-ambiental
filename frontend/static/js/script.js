
/*
  BIOPRESERVE FÁCIL — SENAI

  - Dados reais do MySQL via Flask
  - Gráfico com médias de 1 em 1 hora
  - Interpolação visual de até 2 horas vazias
  - Histórico com todas as leituras recebidas
  - Índice experimental de preservação
  - Atualização a cada 30 segundos
*/

let leituras = [];
let limites = {};
let grafico = null;
let periodoDias = 1;

const HORA = 60 * 60 * 1000;
const MAX_LACUNA = 2;

const INDICADORES = [
  "temperature",
  "humidity",
  "CO2",
  "particula1",
  "particula2"
];

const $ = id => document.getElementById(id);

// =======================================
// FUNÇÕES AUXILIARES
// =======================================

function valorNumerico(valor) {
  if (
    valor === null ||
    valor === undefined ||
    valor === ""
  ) return null;

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
  if (valor === null || valor === undefined || valor === "") {
    return null;
  }

  if (typeof valor === "number") {
    const data = new Date(
      valor < 1e12 ? valor * 1000 : valor
    );

    return Number.isNaN(data.getTime()) ? null : data;
  }

  const texto = String(valor).trim();

  const formatoMySQL = texto.match(
    /^(\d{4})-(\d\d)-(\d\d)[ T](\d\d):(\d\d)(?::(\d\d))?$/
  );

  let data;

  if (formatoMySQL) {
    data = new Date(
      Number(formatoMySQL[1]),
      Number(formatoMySQL[2]) - 1,
      Number(formatoMySQL[3]),
      Number(formatoMySQL[4]),
      Number(formatoMySQL[5]),
      Number(formatoMySQL[6] || 0)
    );
  } else {
    data = new Date(texto);
  }

  return Number.isNaN(data.getTime()) ? null : data;
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

function formatarData(data, completo = false) {
  if (!data) return "—";

  return data.toLocaleString(
    "pt-BR",
    completo
      ? {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit"
        }
      : {
          hour: "2-digit",
          minute: "2-digit"
        }
  );
}

function horaCheia(data) {
  const d = new Date(data);
  d.setMinutes(0, 0, 0);
  return d.getTime();
}

function arrayResposta(dados, chave) {
  if (Array.isArray(dados)) return dados;

  for (const nome of [
    chave,
    "dados",
    "registros",
    "resultados",
    "items",
    "medicoes",
    "leituras"
  ]) {
    if (Array.isArray(dados?.[nome])) {
      return dados[nome];
    }
  }

  return [];
}

// =======================================
// CONSULTAS À API
// =======================================

async function consultar(nome) {
  const resposta = await fetch(
    "/dados/" + nome,
    { cache: "no-store" }
  );

  if (!resposta.ok) {
    throw new Error(
      `Erro em ${nome}: HTTP ${resposta.status}`
    );
  }

  return resposta.json();
}

// =======================================
// LIMITES AMBIENTAIS
// =======================================

function estado(campo, valor) {
  const n = valorNumerico(valor);
  const limite = limites[campo];

  if (n === null || !limite) {
    return {
      texto: "Sem avaliação",
      classe: ""
    };
  }

  if (
    (limite.min !== null && n < limite.min) ||
    (limite.max !== null && n > limite.max)
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

function preencherStatus(id, situacao) {
  $(id).className = "tag " + situacao.classe;
  $(id).textContent = situacao.texto;
}

async function carregarLimites() {
  const resposta = await consultar("limites");
  const lista = arrayResposta(resposta, "limites");

  limites = {};

  for (const item of lista) {
    if (
      [false, 0, "0", "false", "False"]
        .includes(item.ativo)
    ) {
      continue;
    }

    const campo =
      item.campo ?? item.indicador_campo;

    if (!INDICADORES.includes(campo)) {
      continue;
    }

    const min = valorNumerico(item.valor_minimo);
    const max = valorNumerico(item.valor_maximo);

    if (min === null && max === null) continue;

    limites[campo] = { min, max };
  }

  const umidade = limites.humidity;

  $("faixa-umidade").textContent = umidade
    ? `Faixa operacional: ${umidade.min ?? "—"}% a ${umidade.max ?? "—"}%`
    : "Faixa operacional não cadastrada";
}

// =======================================
// AMBIENTES
// =======================================

async function carregarAmbientes() {
  const resposta = await consultar("ambientes");
  const lista = arrayResposta(resposta, "ambientes");

  const seletor = $("ambiente");
  seletor.replaceChildren();

  if (!lista.length) {
    seletor.add(new Option("Biblioteca", ""));
    return;
  }

  for (const item of lista) {
    seletor.add(
      new Option(
        item.nome ?? "Ambiente",
        item.id ?? ""
      )
    );
  }

  // Não permitir selecionar um ambiente que
  // o backend ainda não consegue filtrar.
  seletor.disabled = true;
  seletor.title =
    "Filtro por ambiente ainda não integrado à API";
}

// =======================================
// CARD DE TEMPERATURA
// =======================================

function preencherTemperatura(dados) {
  const temperatura = valorNumerico(dados.temperature);

  $("temperatura").textContent =
    numero(temperatura) + "°C";

  const marcador = $("marcador-temperatura");

  if (temperatura === null) {
    preencherStatus("status-temperatura", {
      texto: "Sem leitura",
      classe: ""
    });

    marcador.style.display = "none";
    $("posicao-temperatura").textContent =
      "Aguardando leitura";

    return;
  }

  const operacional = estado(
    "temperature",
    temperatura
  );

  let situacao;

  if (operacional.texto === "Alerta") {
    situacao = operacional;
  } else if (
    temperatura >= 18 &&
    temperatura <= 22
  ) {
    situacao = {
      texto: "Agradável",
      classe: "ok"
    };
  } else {
    situacao = {
      texto: "Fora do ideal",
      classe: "alerta"
    };
  }

  preencherStatus("status-temperatura", situacao);

  const porcentagem = Math.max(
    0,
    Math.min(
      100,
      ((temperatura - 15) / 11) * 100
    )
  );

  marcador.style.left = porcentagem + "%";
  marcador.style.display = "block";

  $("posicao-temperatura").textContent =
    `▲ Você está aqui (${numero(temperatura)}°)`;
}

// =======================================
// CARD DE UMIDADE
// =======================================

function preencherUmidade(dados) {
  const umidade = valorNumerico(dados.humidity);
  const limite = limites.humidity;

  $("umidade").textContent =
    numero(umidade, 0) + "%";

  preencherStatus(
    "status-umidade",
    estado("humidity", umidade)
  );

  $("risco-ressecamento").textContent =
    umidade === null || !limite
      ? "—"
      : limite.min !== null &&
        umidade < limite.min
      ? "Atenção"
      : "Baixo";

  $("risco-mofo").textContent =
    umidade === null || !limite
      ? "—"
      : limite.max !== null &&
        umidade > limite.max
      ? "Atenção"
      : "Baixo";
}

// =======================================
// CARD DO AR
// =======================================

function preencherAr(dados) {
  const co2 = valorNumerico(dados.CO2);

  $("co2").textContent =
    "CO₂: " + numero(co2, 0) + " ppm";

  $("particulas").textContent =
    `Partículas: ${numero(dados.particula1)} / ` +
    numero(dados.particula2);

  const situacao = estado("CO2", co2);

  $("qualidade-ar").textContent =
    situacao.texto === "Adequado"
      ? "Puro & Fresco"
      : situacao.texto === "Alerta"
      ? "Atenção ao Ar"
      : "Sem avaliação";

  preencherStatus("situacao-ar", situacao);
}

// =======================================
// ÍNDICE EXPERIMENTAL
// =======================================

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

function preencherIndice(dados) {
  const notas = INDICADORES
    .map(campo =>
      pontuacaoIndicador(
        dados[campo],
        limites[campo]
      )
    )
    .filter(n => n !== null);

  const marcador = $("gauge-marker");

  if (!notas.length) {
    $("indice").textContent = "—";

    $("nivel-preservacao").textContent =
      "Sem dados suficientes";

    $("indice-detalhe").textContent =
      "Configure leituras e limites válidos";

    marcador.setAttribute("visibility", "hidden");
    return;
  }

  const media = notas.reduce(
    (soma, nota) => soma + nota,
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
      ? "Atenção às condições"
      : "Condições críticas";

  $("nivel-preservacao").className =
    "tag gauge-legenda " +
    (media >= 85
      ? "verde"
      : media < 60
      ? "alerta"
      : "");

  $("indice-detalhe").textContent =
    `Estimativa experimental • ${notas.length}/5 indicadores`;

  const angulo = Math.PI * (1 - media / 100);

  const x = 90 + 69 * Math.cos(angulo);
  const y = 96 - 69 * Math.sin(angulo);

  marcador.setAttribute("cx", x.toFixed(2));
  marcador.setAttribute("cy", y.toFixed(2));
  marcador.setAttribute("visibility", "visible");
}

// =======================================
// STATUS GERAL
// =======================================

function preencherCards(dados, kpis) {
  preencherTemperatura(dados);
  preencherUmidade(dados);
  preencherAr(dados);
  preencherIndice(dados);

  const abertos = valorNumerico(
    kpis?.ocorrencias_abertas
  );

  $("mensagem-central").textContent =
    abertos === null
      ? "Ocorrências indisponíveis"
      : abertos === 0
      ? "Nenhuma ocorrência ambiental aberta"
      : `${abertos} ocorrência(s) ambiental(is) aberta(s)`;

  $("status-central").style.borderColor =
    abertos === 0 ? "#065f46" : "#92400e";

  $("resumo-dia").textContent =
    abertos === null
      ? "Não foi possível consultar as ocorrências."
      : abertos === 0
      ? "Não existem ocorrências abertas no banco. Verifique a data da última leitura."
      : `Existem ${abertos} ocorrência(s) abertas registradas no banco.`;

  const data = dataLeitura(dados);

  $("ultima-atualizacao").textContent =
    data
      ? "Leitura: " + formatarData(data, true)
      : "Data da leitura indisponível";
}

// =======================================
// HISTÓRICO — TODAS AS LEITURAS
// =======================================

function preencherTabela() {
  const tbody = $("tabela-leituras");
  tbody.replaceChildren();

  if (!leituras.length) {
    const linha = document.createElement("tr");
    const coluna = document.createElement("td");

    coluna.colSpan = 4;
    coluna.textContent =
      "Nenhuma medição encontrada.";

    linha.appendChild(coluna);
    tbody.appendChild(linha);

    $("total-leituras").textContent =
      "Nenhuma leitura recebida";
    return;
  }

  const fragmento = document.createDocumentFragment();

  // Não usamos mais slice(0, 5).
  // Todos os registros retornados pela API entram na tabela.
  for (const item of leituras) {
    const linha = document.createElement("tr");

    const valores = [
      formatarData(dataLeitura(item), true),
      numero(item.temperature) + " °C",
      numero(item.humidity, 0) + "%"
    ];

    for (const valor of valores) {
      const coluna = document.createElement("td");
      coluna.textContent = valor;
      linha.appendChild(coluna);
    }

    const temperatura = estado(
      "temperature",
      item.temperature
    );

    const umidade = estado(
      "humidity",
      item.humidity
    );

    const colunaSituacao =
      document.createElement("td");

    const tag = document.createElement("span");

    const semAvaliacao =
      temperatura.texto === "Sem avaliação" ||
      umidade.texto === "Sem avaliação";

    const alerta =
      temperatura.texto === "Alerta" ||
      umidade.texto === "Alerta";

    tag.className = "tag " +
      (semAvaliacao
        ? ""
        : alerta
        ? "alerta"
        : "ok");

    tag.textContent = semAvaliacao
      ? "Sem avaliação"
      : alerta
      ? "Atenção"
      : "Adequado";

    colunaSituacao.appendChild(tag);
    linha.appendChild(colunaSituacao);
    fragmento.appendChild(linha);
  }

  tbody.appendChild(fragmento);

  $("total-leituras").textContent =
    `${leituras.length} leituras exibidas — todas as recebidas da API`;
}

// =======================================
// MÉDIAS HORÁRIAS REAIS
// =======================================

function agregarPorHora(itens) {
  const grupos = new Map();

  for (const item of itens) {
    const data = dataLeitura(item);

    if (!data) continue;

    const hora = horaCheia(data);

    if (!grupos.has(hora)) {
      grupos.set(hora, {
        x: hora,
        somaTemperatura: 0,
        qtdTemperatura: 0,
        somaUmidade: 0,
        qtdUmidade: 0,
        quantidade: 0
      });
    }

    const grupo = grupos.get(hora);

    grupo.quantidade++;

    const temperatura = valorNumerico(
      item.temperature
    );

    const umidade = valorNumerico(
      item.humidity
    );

    if (temperatura !== null) {
      grupo.somaTemperatura += temperatura;
      grupo.qtdTemperatura++;
    }

    if (umidade !== null) {
      grupo.somaUmidade += umidade;
      grupo.qtdUmidade++;
    }
  }

  return [...grupos.values()]
    .sort((a, b) => a.x - b.x)
    .map(grupo => ({
      x: grupo.x,

      temperatura: grupo.qtdTemperatura
        ? grupo.somaTemperatura / grupo.qtdTemperatura
        : null,

      umidade: grupo.qtdUmidade
        ? grupo.somaUmidade / grupo.qtdUmidade
        : null,

      quantidade: grupo.quantidade
    }));
}

// =======================================
// COMPLETAR HORAS SEM MEDIÇÕES
// =======================================

function preencherLacunas(pontos) {
  if (!pontos.length) return [];

  const mapa = new Map(
    pontos.map(p => [p.x, p])
  );

  const primeiro = pontos[0].x;
  const ultimo = pontos[pontos.length - 1].x;

  const resultado = [];

  for (let hora = primeiro; hora <= ultimo; hora += HORA) {
    const real = mapa.get(hora);

    if (real) {
      resultado.push({
        ...real,
        estimadoTemperatura: false,
        estimadoUmidade: false
      });
    } else {
      resultado.push({
        x: hora,
        temperatura: null,
        umidade: null,
        quantidade: 0,
        estimadoTemperatura: false,
        estimadoUmidade: false
      });
    }
  }

  // Interpolação apenas entre horas reais,
  // com no máximo 2 horas faltantes.
  for (const campo of ["temperatura", "umidade"]) {
    let indice = 0;

    while (indice < resultado.length) {
      if (resultado[indice][campo] !== null) {
        indice++;
        continue;
      }

      const inicio = indice;

      while (
        indice < resultado.length &&
        resultado[indice][campo] === null
      ) {
        indice++;
      }

      const fim = indice - 1;
      const quantidade = fim - inicio + 1;

      const anterior = resultado[inicio - 1];
      const proximo = resultado[indice];

      if (
        !anterior ||
        !proximo ||
        anterior[campo] === null ||
        proximo[campo] === null ||
        quantidade > MAX_LACUNA
      ) {
        continue;
      }

      const diferenca =
        proximo[campo] - anterior[campo];

      for (let j = 0; j < quantidade; j++) {
        const proporcao =
          (j + 1) / (quantidade + 1);

        const ponto = resultado[inicio + j];

        ponto[campo] =
          anterior[campo] + diferenca * proporcao;

        if (campo === "temperatura") {
          ponto.estimadoTemperatura = true;
        } else {
          ponto.estimadoUmidade = true;
        }
      }
    }
  }

  return resultado;
}

// =======================================
// FAIXA DE CONFORTO 18–22°C
// =======================================

const pluginConforto = {
  id: "faixaConforto",

  beforeDatasetsDraw(chart) {
    if (!chart.$mostrarTemperatura) return;

    const escala = chart.scales.temp;
    const area = chart.chartArea;

    if (!escala || !area) return;

    const limitar = y => Math.max(
      area.top,
      Math.min(area.bottom, y)
    );

    const topo = limitar(
      escala.getPixelForValue(22)
    );

    const baixo = limitar(
      escala.getPixelForValue(18)
    );

    const ctx = chart.ctx;

    ctx.save();

    ctx.fillStyle = "rgba(16,185,129,.09)";
    ctx.fillRect(
      area.left,
      topo,
      area.right - area.left,
      Math.max(0, baixo - topo)
    );

    ctx.strokeStyle = "rgba(52,211,153,.30)";
    ctx.setLineDash([4, 4]);

    for (const y of [topo, baixo]) {
      ctx.beginPath();
      ctx.moveTo(area.left, y);
      ctx.lineTo(area.right, y);
      ctx.stroke();
    }

    ctx.setLineDash([]);

    ctx.font = "10px Arial";
    ctx.fillStyle = "#6ee7b7";

    ctx.fillText(
      "Faixa ideal 18–22°C",
      area.left + 8,
      Math.min(area.bottom - 8, topo + 15)
    );

    ctx.restore();
  }
};

// =======================================
// GRÁFICO
// =======================================

function mensagemGrafico(texto) {
  const elemento = $("aviso-grafico");

  elemento.textContent = texto;
  elemento.style.display = texto ? "flex" : "none";
}

function desenharGrafico() {
  if (grafico) {
    grafico.destroy();
    grafico = null;
  }

  if (typeof Chart === "undefined") {
    mensagemGrafico(
      "Não foi possível carregar a biblioteca do gráfico."
    );
    return;
  }

  if (!leituras.length) {
    mensagemGrafico(
      "Nenhuma medição disponível na API."
    );
    return;
  }

  const agora = new Date();

  const inicioHoje = new Date(
    agora.getFullYear(),
    agora.getMonth(),
    agora.getDate()
  );

  const inicioPeriodo = periodoDias === 1
    ? inicioHoje.getTime()
    : Date.now() - periodoDias * 24 * HORA;

  let filtradas = leituras.filter(item => {
    const data = dataLeitura(item);

    return data &&
      data.getTime() >= inicioPeriodo &&
      data.getTime() <= Date.now();
  });

  let historicoAnterior = false;

  // Se o período estiver vazio, exibimos
  // o último dia com registros disponíveis,
  // informando claramente que é histórico.
  if (!filtradas.length) {
    const ultimaData = dataLeitura(leituras[0]);

    if (!ultimaData) {
      mensagemGrafico("Datas inválidas nas medições.");
      return;
    }

    const inicioHistorico =
      ultimaData.getTime() - 24 * HORA;

    filtradas = leituras.filter(item => {
      const data = dataLeitura(item);

      return data &&
        data.getTime() >= inicioHistorico &&
        data.getTime() <= ultimaData.getTime();
    });

    historicoAnterior = true;
  }

  const mediasReais = agregarPorHora(filtradas);
  const pontos = preencherLacunas(mediasReais);

  if (!pontos.length) {
    mensagemGrafico(
      "Não há temperatura ou umidade para exibir."
    );
    return;
  }

  mensagemGrafico("");

  const metrica = $("metrica").value;
  const datasets = [];

  const ctx = $("grafico").getContext("2d");

  const gradiente = ctx.createLinearGradient(
    0, 0, 0, 310
  );

  gradiente.addColorStop(
    0,
    "rgba(255,149,0,.25)"
  );

  gradiente.addColorStop(
    1,
    "rgba(255,149,0,0)"
  );

  function datasetDo(campo, label, cor, eixo) {
    const estimado =
      campo === "temperatura"
        ? "estimadoTemperatura"
        : "estimadoUmidade";

    return {
      label,
      yAxisID: eixo,

      data: pontos.map(p => ({
        x: p.x,
        y: p[campo],
        estimado: p[estimado],
        quantidade: p.quantidade
      })),

      borderColor: cor,

      backgroundColor: campo === "temperatura"
        ? gradiente
        : "rgba(0,210,255,.04)",

      borderWidth: campo === "temperatura" ? 3 : 2.5,

      fill: campo === "temperatura" ? "origin" : false,

      tension: 0.35,
      cubicInterpolationMode: "monotone",

      spanGaps: false,

      pointRadius: contexto => {
        const bruto = contexto.raw;

        if (!bruto || bruto.y === null) return 0;

        if (bruto.estimado) return 3;

        return pontos.length <= 24 ? 3 : 1.5;
      },

      pointBackgroundColor: contexto => {
        const bruto = contexto.raw;

        return bruto?.estimado
          ? "#0b1525"
          : cor;
      },

      pointBorderColor: cor,
      pointBorderWidth: 1.5,
      pointHoverRadius: 6,

      segment: {
        borderDash: contexto => {
          const anterior =
            contexto.p0?.$context?.raw;

          const atual =
            contexto.p1?.$context?.raw;

          return anterior?.estimado ||
                 atual?.estimado
            ? [5, 5]
            : [];
        }
      }
    };
  }

  if (
    metrica === "ambos" ||
    metrica === "temperature"
  ) {
    datasets.push(
      datasetDo(
        "temperatura",
        "Temperatura (°C)",
        "#ff9500",
        "temp"
      )
    );
  }

  if (
    metrica === "ambos" ||
    metrica === "humidity"
  ) {
    datasets.push(
      datasetDo(
        "umidade",
        "Umidade (%)",
        "#00d2ff",
        "umid"
      )
    );
  }

  const temperaturas = pontos
    .map(p => p.temperatura)
    .filter(v => v !== null);

  const minimoTemperatura = temperaturas.length
    ? Math.min(17, ...temperaturas) - 1
    : 15;

  const maximoTemperatura = temperaturas.length
    ? Math.max(26, ...temperaturas) + 1
    : 27;

  const minimoX = pontos[0].x;
  const maximoX = pontos[pontos.length - 1].x;

  grafico = new Chart(ctx, {
    type: "line",

    plugins: [pluginConforto],

    data: { datasets },

    options: {
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      normalized: true,

      animation: {
        duration: 450
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
          padding: 12,

          callbacks: {
            title: itens => {
              if (!itens.length) return "";

              return formatarData(
                new Date(itens[0].parsed.x),
                true
              );
            },

            label: item => {
              const bruto = item.raw;

              const unidade =
                item.dataset.yAxisID === "temp"
                  ? "°C"
                  : "%";

              const tipo = bruto.estimado
                ? " — estimativa interpolada"
                : " — média de medições reais";

              return (
                item.dataset.label + ": " +
                numero(item.parsed.y) +
                unidade +
                tipo
              );
            }
          }
        }
      },

      scales: {
        x: {
          type: "linear",

          // Cada ponto é uma hora.
          // A escala trabalha em passos de 1 hora.
          min: minimoX - HORA / 2,
          max: maximoX + HORA / 2,

          grid: {
            color: "rgba(35,50,77,.40)"
          },

          border: {
            display: false
          },

          ticks: {
            stepSize: HORA,
            maxTicksLimit: 9,
            maxRotation: 0,
            autoSkip: true,
            color: "#94a3b8",

            callback: valor => {
              const d = new Date(valor);

              return periodoDias === 1 &&
                     !historicoAnterior
                ? formatarData(d)
                : d.toLocaleString("pt-BR", {
                    day: "2-digit",
                    month: "2-digit",
                    hour: "2-digit"
                  }) + "h";
            }
          }
        },

        temp: {
          type: "linear",
          position: "left",
          display: metrica !== "humidity",

          suggestedMin: minimoTemperatura,
          suggestedMax: maximoTemperatura,

          grid: {
            color: "rgba(35,50,77,.42)"
          },

          border: {
            display: false
          },

          ticks: {
            color: "#94a3b8",
            callback: valor => valor + "°C"
          }
        },

        umid: {
          type: "linear",
          position: "right",
          display: metrica !== "temperature",

          min: 0,
          max: 100,

          grid: {
            drawOnChartArea:
              metrica === "humidity",

            color: "rgba(35,50,77,.42)"
          },

          border: {
            display: false
          },

          ticks: {
            color: "#94a3b8",
            callback: valor => valor + "%"
          }
        }
      }
    }
  });

  grafico.$mostrarTemperatura =
    metrica !== "humidity";

  const estimativas = pontos.filter(
    p => p.estimadoTemperatura ||
         p.estimadoUmidade
  ).length;

  const primeiro = new Date(minimoX);
  const ultimo = new Date(maximoX);

  const descricao =
    `${filtradas.length} medições reais, ` +
    `${mediasReais.length} horas com registros, ` +
    `${estimativas} hora(s) com interpolação visual.`;

  $("observacao-grafico").textContent =
    historicoAnterior
      ? `Sem medições no período selecionado. ` +
        `Exibindo histórico de ${formatarData(primeiro, true)} ` +
        `a ${formatarData(ultimo, true)}. ${descricao}`
      : `Médias calculadas de 1 em 1 hora. ${descricao}`;

  $("observacao-grafico").style.color =
    historicoAnterior
      ? "#fbbf24"
      : "#34d399";
}

// =======================================
// CARREGAMENTO PRINCIPAL
// =======================================

async function atualizar() {
  try {
    const [
      ultima,
      historico,
      kpis
    ] = await Promise.all([
      consultar("ultima"),
      consultar("leituras"),
      consultar("kpis")
    ]);

    leituras = arrayResposta(
      historico,
      "leituras"
    )
      .filter(item => dataLeitura(item))
      .sort(
        (a, b) =>
          dataLeitura(b) - dataLeitura(a)
      );

    const ultimaLeitura =
      ultima?.leitura ??
      ultima?.ultima ??
      ultima?.medicao ??
      ultima;

    preencherCards(ultimaLeitura, kpis);
    preencherTabela();
    desenharGrafico();

    $("sensor-status").textContent =
      `${leituras.length} leituras`;

    $("sensor-status").className =
      "tag cyan";

  } catch (erro) {
    console.error(erro);

    $("mensagem-central").textContent =
      "Erro ao consultar a API Flask";

    $("sensor-status").textContent =
      "Sem conexão";

    $("sensor-status").className =
      "tag alerta";

    $("observacao-grafico").textContent =
      "Verifique o backend na porta 8080.";
  }
}

// =======================================
// EVENTOS
// =======================================

document.querySelectorAll(
  "[data-periodo]"
).forEach(botao => {
  botao.addEventListener("click", () => {
    periodoDias = Number(botao.dataset.periodo);

    document.querySelectorAll(
      "[data-periodo]"
    ).forEach(item => {
      item.classList.toggle(
        "ativo",
        item === botao
      );
    });

    desenharGrafico();
  });
});

$("metrica").addEventListener(
  "change",
  desenharGrafico
);

$("atualizar").addEventListener(
  "click",
  atualizar
);

$("relatar-problema").addEventListener(
  "click",
  () => {
    alert(
      "Registro manual ainda não implementado."
    );
  }
);

async function iniciar() {
  const resultados = await Promise.allSettled([
    carregarLimites(),
    carregarAmbientes()
  ]);

  resultados.forEach(resultado => {
    if (resultado.status === "rejected") {
      console.warn(
        "Erro de configuração:",
        resultado.reason
      );
    }
  });

  await atualizar();
}

iniciar();

setInterval(atualizar, 30000);
