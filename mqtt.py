# ********************* CONEXÃO SENSORES *********************************
# Legenda das marcações neste arquivo:
#   [ORIGINAL]  trecho do seu código, mantido
#   [AJUSTE]    alteração mínima em trecho original
#   [NOVO]      acrescentado (imports, modelos, fila de gravação, API)

import json
import logging
import math
import os
import queue
import threading
from datetime import datetime, timezone
from urllib.parse import quote_plus

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

try:  # opcional: carrega variáveis de um arquivo .env, se python-dotenv estiver instalado
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ----------------------------------------------------------------------
# [NOVO] Logs
# ----------------------------------------------------------------------
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("monitoramento")

# ----------------------------------------------------------------------
# [NOVO] Configurações (tudo via variáveis de ambiente; os padrões abaixo
# repetem o que já existia no código original)
# ----------------------------------------------------------------------
MQTT_BROKER = os.environ.get("MQTT_BROKER", "test.mosquitto.org")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "projeto_integrado/SENAI134/Cienciadedados/GrupoX")
MQTT_USER = os.environ.get("MQTT_USER")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
MQTT_TLS = os.environ.get("MQTT_TLS", "false").lower() == "true"
# client_id fixo + sessão persistente ajudam a receber mensagens QoS 1 após uma queda
MQTT_CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "senai134-grupox-monitoramento-api")

# Enquanto os acessos reais das caixinhas não existem, tudo é ligado a este sensor.
SENSOR_CODIGO_PADRAO = os.environ.get("SENSOR_CODIGO", "IOT_PADRAO")

# Quando cada caixinha tiver seu acesso (tópico próprio), preencha aqui:
#   "projeto_integrado/SENAI134/Cienciadedados/GrupoX/caixinha1": "codigo_na_tabela_sensor"
TOPICO_PARA_SENSOR = {}

ARQUIVO_REJEITADAS = os.environ.get("REJEITADAS_ARQUIVO", "mensagens_rejeitadas.jsonl")
TAMANHO_FILA = int(os.environ.get("FILA_TAMANHO", 10000))


def _montar_uri_banco():
    url = os.environ.get("DATABASE_URL")  # permite sobrescrever (ex.: testes)
    if url:
        return url
    user = quote_plus(os.environ.get("DB_USER", "root"))
    senha = quote_plus(os.environ.get("DB_PASSWORD", ""))
    host = os.environ.get("DB_HOST", "127.0.0.1")
    porta = os.environ.get("DB_PORT", "3306")
    nome = os.environ.get("DB_NAME", "monitoramento_bd")
    return f"mysql+pymysql://{user}:{senha}@{host}:{porta}/{nome}"


# ----------------------------------------------------------------------
# [NOVO] Flask, SQLAlchemy e modelos (mapeiam as tabelas do DDL)
# ----------------------------------------------------------------------
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = _montar_uri_banco()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 280}
if hasattr(app, "json"):
    app.json.sort_keys = False

mybd = SQLAlchemy(app)


class Sensor(mybd.Model):
    __tablename__ = "sensor"
    id = mybd.Column(mybd.Integer, primary_key=True)
    id_ambiente = mybd.Column(mybd.Integer, nullable=False)
    nome = mybd.Column(mybd.String(100))
    modelo = mybd.Column(mybd.String(50))
    codigo = mybd.Column(mybd.String(50), nullable=False, unique=True)
    ativo = mybd.Column(mybd.Boolean, default=True)
    data_instalacao = mybd.Column(mybd.DateTime)


class Registro(mybd.Model):
    """Tabela `medicao`, com os nomes de campo exigidos pelas diretrizes."""
    __tablename__ = "medicao"
    __table_args__ = (UniqueConstraint("id_sensor", "registro_tempo", name="uq_medicao_sensor_tempo"),)

    id = mybd.Column(mybd.BigInteger().with_variant(mybd.Integer, "sqlite"), primary_key=True)
    id_sensor = mybd.Column(mybd.Integer, mybd.ForeignKey("sensor.id"), nullable=False)
    temperature = mybd.Column(mybd.Numeric(10, 2))
    humidity = mybd.Column(mybd.Numeric(10, 2))
    CO2 = mybd.Column("CO2", mybd.Numeric(10, 2))
    particula1 = mybd.Column(mybd.Numeric(10, 2))
    particula2 = mybd.Column(mybd.Numeric(10, 2))
    registro_tempo = mybd.Column(mybd.DateTime, nullable=False, index=True)  # sempre em UTC


CAMPOS_MEDIDOS = ("temperature", "humidity", "CO2", "particula1", "particula2")


def _num(valor):
    return None if valor is None else float(valor)


def _fmt_dt(dt):
    return None if dt is None else dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def registro_para_dict(registro, codigo_sensor=None):
    return {
        "id": registro.id,
        "sensor": codigo_sensor,
        "temperature": _num(registro.temperature),
        "humidity": _num(registro.humidity),
        "CO2": _num(registro.CO2),
        "particula1": _num(registro.particula1),
        "particula2": _num(registro.particula2),
        "registro_tempo": _fmt_dt(registro.registro_tempo),
    }


# ----------------------------------------------------------------------
# [NOVO] Estatísticas, fila de gravação e arquivo de mensagens rejeitadas
# ----------------------------------------------------------------------
_stats_lock = threading.Lock()
estatisticas = {
    "conectado": False,
    "ultima_conexao": None,
    "ultima_desconexao": None,
    "ultima_mensagem": None,
    "recebidas": 0,
    "invalidas": 0,
    "enfileiradas": 0,
    "gravadas": 0,
    "duplicadas": 0,
    "erros_gravacao": 0,
    "rejeitadas_arquivo": 0,
}


def _stat(chave, valor=None):
    with _stats_lock:
        if valor is None:
            estatisticas[chave] += 1
        else:
            estatisticas[chave] = valor


fila_gravacao = queue.Queue(maxsize=TAMANHO_FILA)
_parar = threading.Event()
_arquivo_lock = threading.Lock()
_worker_thread = None


def registrar_rejeitada(motivo, payload, topico):
    """Guarda em arquivo a mensagem que não pôde ser gravada, para análise posterior."""
    linha = {
        "quando": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "motivo": motivo,
        "topico": topico,
        "payload": payload,
    }
    try:
        with _arquivo_lock, open(ARQUIVO_REJEITADAS, "a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
        _stat("rejeitadas_arquivo")
    except OSError as e:
        logger.error("Não foi possível salvar mensagem rejeitada em arquivo: %s", e)


def identificar_sensor(topico):
    """Define qual sensor (campo `codigo` da tabela sensor) enviou a mensagem."""
    return TOPICO_PARA_SENSOR.get(topico, SENSOR_CODIGO_PADRAO)


def validar_payload(dados):
    """Valida o JSON recebido. Retorna (valores, registro_tempo_utc_naive, erro)."""
    if not isinstance(dados, dict):
        return None, None, "payload não é um objeto JSON"

    ts = dados.get("timestamp")
    if ts is None or isinstance(ts, bool):
        return None, None, "timestamp ausente ou inválido"
    try:
        ts = int(ts)
        if ts > 10**11:  # valor em milissegundos
            ts //= 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None, None, f"timestamp inválido: {dados.get('timestamp')!r}"
    agora = datetime.now(timezone.utc)
    if dt < datetime(2000, 1, 1, tzinfo=timezone.utc) or (dt - agora).days >= 1:
        return None, None, f"timestamp fora de faixa plausível: {dt.isoformat()}"

    valores = {}
    for campo in CAMPOS_MEDIDOS:
        v = dados.get(campo)
        if v is None:
            valores[campo] = None  # valor ausente é permitido (coluna aceita NULL)
            continue
        if isinstance(v, bool):
            return None, None, f"{campo} inválido: {v!r}"
        try:
            v = float(v)
        except (ValueError, TypeError):
            return None, None, f"{campo} não numérico: {v!r}"
        if not math.isfinite(v) or abs(v) >= 10**8:
            return None, None, f"{campo} fora do limite aceito: {v!r}"
        valores[campo] = round(v, 2)

    if all(v is None for v in valores.values()):
        return None, None, "nenhuma medição presente no payload"

    return valores, dt.replace(tzinfo=None), None


def _eh_duplicidade(erro):
    orig = getattr(erro, "orig", None)
    args = getattr(orig, "args", ())
    return (args and args[0] == 1062) or "UNIQUE constraint failed" in str(erro)


def _gravar_com_retry(item):
    """Grava um item; se o banco estiver indisponível, tenta de novo (backoff até 60s)."""
    espera = 2
    while not _parar.is_set():
        with app.app_context():
            try:
                sensor = Sensor.query.filter_by(codigo=item["codigo_sensor"]).first()
                if sensor is None:
                    logger.error("Sensor '%s' não cadastrado na tabela sensor", item["codigo_sensor"])
                    registrar_rejeitada(f"sensor '{item['codigo_sensor']}' não cadastrado",
                                        item["payload"], item["topico"])
                    return
                mybd.session.add(Registro(
                    id_sensor=sensor.id,
                    registro_tempo=item["registro_tempo"],
                    **item["valores"],
                ))
                mybd.session.commit()
                _stat("gravadas")
                logger.info("Dados inseridos no banco de dados com sucesso (sensor=%s, tempo=%s)",
                            item["codigo_sensor"], item["registro_tempo"])
                return
            except IntegrityError as e:
                mybd.session.rollback()
                if _eh_duplicidade(e):
                    _stat("duplicadas")
                    logger.warning("Leitura duplicada ignorada (sensor=%s, tempo=%s)",
                                   item["codigo_sensor"], item["registro_tempo"])
                else:
                    _stat("erros_gravacao")
                    logger.error("Violação de integridade ao gravar: %s", e)
                    registrar_rejeitada(f"integridade: {e}", item["payload"], item["topico"])
                return
            except SQLAlchemyError as e:  # banco fora do ar, timeout etc.: tenta de novo
                mybd.session.rollback()
                _stat("erros_gravacao")
                logger.error("Falha ao gravar no banco (nova tentativa em %ss): %s", espera, e)
            except Exception as e:  # erro inesperado: não trava a fila
                mybd.session.rollback()
                _stat("erros_gravacao")
                logger.exception("Erro inesperado ao gravar: %s", e)
                registrar_rejeitada(f"erro inesperado: {e}", item["payload"], item["topico"])
                return
        _parar.wait(espera)
        espera = min(espera * 2, 60)


def _worker_gravacao():
    while not _parar.is_set():
        try:
            item = fila_gravacao.get(timeout=1)
        except queue.Empty:
            continue
        try:
            _gravar_com_retry(item)
        finally:
            fila_gravacao.task_done()


def iniciar_worker():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _parar.clear()
        _worker_thread = threading.Thread(target=_worker_gravacao, name="worker-gravacao", daemon=True)
        _worker_thread.start()
        logger.info("Worker de gravação iniciado")


# ----------------------------------------------------------------------
# [ORIGINAL] Callbacks MQTT
# ----------------------------------------------------------------------
mqtt_data = {}

def on_connect(client, userdata, flags, rc):
    # client: A instância do cliente MQTT.
    # userdata: Dados do usuário definidos quando o cliente foi configurado (geralmente None).
    # flags: Dicionário contendo sinalizadores de resposta do broker.
    # rc: Código de resultado da conexão (0 significa sucesso; valores diferentes de zero indicam erros).
    print("Connected with result code " + str(rc))
    if rc == 0:  # [NOVO] estado da conexão para o endpoint de status
        _stat("conectado", True)
        _stat("ultima_conexao", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    client.subscribe(MQTT_TOPIC, qos=1)  # [AJUSTE] tópico vem da config (mesmo valor) e QoS 1

def on_disconnect(client, userdata, rc):  # [NOVO]
    _stat("conectado", False)
    _stat("ultima_desconexao", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    logger.warning("Desconectado do broker MQTT (rc=%s). Reconexão automática ativa.", rc)

def on_message(client, userdata, msg):
    global mqtt_data
    _stat("recebidas")
    _stat("ultima_mensagem", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    # [AJUSTE] decodificação e json.loads protegidos: mensagem inválida não derruba o callback
    try:
        # Decodifica a mensagem recebida de bytes para string
        payload = msg.payload.decode('utf-8')

        # Converte a string JSON em um dicionário Python
        mqtt_data = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        _stat("invalidas")
        logger.error("Mensagem inválida (não é JSON/UTF-8): %s", e)
        registrar_rejeitada(f"json inválido: {e}", repr(msg.payload[:500]), msg.topic)
        return

    # Imprime a mensagem recebida
    print(f"Received message: {mqtt_data}")

    # [AJUSTE] O banco não é mais acessado nesta thread: valida e envia para a fila,
    # e o worker de gravação faz o commit. Assim o MQTT nunca fica bloqueado.
    try:
        valores, timestamp, erro = validar_payload(mqtt_data)
        if erro:
            _stat("invalidas")
            logger.error("Payload rejeitado: %s", erro)
            registrar_rejeitada(erro, payload, msg.topic)
            return

        fila_gravacao.put_nowait({
            "codigo_sensor": identificar_sensor(msg.topic),
            "valores": valores,          # temperature, humidity, CO2, particula1, particula2
            "registro_tempo": timestamp,  # timestamp do MQTT -> registro_tempo
            "payload": payload,
            "topico": msg.topic,
        })
        _stat("enfileiradas")

    except queue.Full:
        _stat("erros_gravacao")
        logger.error("Fila de gravação cheia; mensagem salva em arquivo")
        registrar_rejeitada("fila cheia", payload, msg.topic)
    except Exception as e:
        logger.exception("Erro ao processar os dados do MQTT: %s", e)
        registrar_rejeitada(f"erro: {e}", payload, msg.topic)


def _criar_cliente():  # [AJUSTE] compatível com paho-mqtt 1.x e 2.x; sessão persistente
    kwargs = dict(client_id=MQTT_CLIENT_ID, clean_session=False)
    if hasattr(mqtt, "CallbackAPIVersion"):
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, **kwargs)
    return mqtt.Client(**kwargs)

mqtt_client = _criar_cliente()
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message
if MQTT_USER:
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
if MQTT_TLS:
    mqtt_client.tls_set()
mqtt_client.reconnect_delay_set(min_delay=1, max_delay=60)
# [AJUSTE] connect_async: se o broker estiver fora do ar a aplicação sobe do mesmo jeito
# e o loop reconecta sozinho (antes: mqtt_client.connect("test.mosquitto.org", 1883, 60))
mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, 60)

def start_mqtt():
    iniciar_worker()  # [NOVO]
    mqtt_client.loop_start()

# CONTEUDO

# ********************* API (começa aqui) *********************************

VARIAVEIS = {c.lower(): c for c in CAMPOS_MEDIDOS}


def _parse_dt(valor, nome):
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"Parâmetro '{nome}' inválido. Use ISO 8601, ex.: 2026-11-17T10:00:00Z")
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _inteiro(nome, padrao, minimo, maximo=None):
    bruto = request.args.get(nome)
    if bruto is None:
        return padrao
    try:
        valor = int(bruto)
    except ValueError:
        raise ValueError(f"Parâmetro '{nome}' deve ser um número inteiro")
    valor = max(minimo, valor)
    return min(valor, maximo) if maximo else valor


def _consulta(codigo_sensor=None):
    """Consulta base com filtros: sensor, inicio, fim (tempos em UTC)."""
    q = mybd.session.query(Registro, Sensor.codigo).join(Sensor, Sensor.id == Registro.id_sensor)
    codigo_sensor = codigo_sensor or request.args.get("sensor")
    if codigo_sensor:
        q = q.filter(Sensor.codigo == codigo_sensor)
    if request.args.get("inicio"):
        q = q.filter(Registro.registro_tempo >= _parse_dt(request.args["inicio"], "inicio"))
    if request.args.get("fim"):
        q = q.filter(Registro.registro_tempo <= _parse_dt(request.args["fim"], "fim"))
    return q


def _listar(q):
    limit = _inteiro("limit", 100, 1, 1000)
    offset = _inteiro("offset", 0, 0)
    ordem = request.args.get("ordem", "desc").lower()
    if ordem not in ("asc", "desc"):
        raise ValueError("Parâmetro 'ordem' deve ser 'asc' ou 'desc'")
    total = q.count()
    coluna = Registro.registro_tempo.asc() if ordem == "asc" else Registro.registro_tempo.desc()
    linhas = q.order_by(coluna, Registro.id).limit(limit).offset(offset).all()
    return jsonify({
        "total": total, "limit": limit, "offset": offset,
        "dados": [registro_para_dict(r, cod) for r, cod in linhas],
    })


@app.route("/health", methods=["GET"])
def health():
    """Verifica API, banco de dados e conexão MQTT."""
    banco_ok = True
    try:
        mybd.session.execute(text("SELECT 1"))
    except SQLAlchemyError as e:
        banco_ok = False
        mybd.session.rollback()
        logger.error("Health check: banco indisponível: %s", e)
    corpo = {
        "status": "ok" if banco_ok else "degradado",
        "api": "ok",
        "banco": "ok" if banco_ok else "erro",
        "mqtt": "conectado" if estatisticas["conectado"] else "desconectado",
    }
    return jsonify(corpo), (200 if banco_ok else 503)


@app.route("/api/leituras", methods=["GET"])
def listar_leituras():
    """Filtros: sensor, inicio, fim, limit (máx. 1000), offset, ordem (asc|desc)."""
    return _listar(_consulta())


@app.route("/api/leituras/ultima", methods=["GET"])
def ultima_leitura():
    """Leitura mais recente (opcional: ?sensor=codigo). Usada para 'leitura atual' e 'última atualização'."""
    linha = _consulta().order_by(Registro.registro_tempo.desc(), Registro.id.desc()).first()
    if linha is None:
        return jsonify({"erro": "Nenhuma leitura encontrada"}), 404
    return jsonify(registro_para_dict(*linha))


@app.route("/api/leituras/<int:id_leitura>", methods=["GET"])
def obter_leitura(id_leitura):
    linha = (mybd.session.query(Registro, Sensor.codigo)
             .join(Sensor, Sensor.id == Registro.id_sensor)
             .filter(Registro.id == id_leitura).first())
    if linha is None:
        return jsonify({"erro": "Leitura não encontrada"}), 404
    return jsonify(registro_para_dict(*linha))


@app.route("/api/sensores", methods=["GET"])
def listar_sensores():
    sensores = Sensor.query.order_by(Sensor.id).all()
    return jsonify([{
        "id": s.id, "codigo": s.codigo, "nome": s.nome, "modelo": s.modelo,
        "id_ambiente": s.id_ambiente, "ativo": bool(s.ativo),
    } for s in sensores])


@app.route("/api/sensores/<codigo>/leituras", methods=["GET"])
def leituras_do_sensor(codigo):
    """Leituras de um sensor específico (filtros: inicio, fim, limit, offset, ordem)."""
    if Sensor.query.filter_by(codigo=codigo).first() is None:
        return jsonify({"erro": f"Sensor '{codigo}' não encontrado"}), 404
    return _listar(_consulta(codigo))


@app.route("/api/historico/<variavel>", methods=["GET"])
def historico_variavel(variavel):
    """Histórico de uma variável (temperature, humidity, CO2, particula1, particula2) para gráficos."""
    campo = VARIAVEIS.get(variavel.lower())
    if campo is None:
        return jsonify({"erro": f"Variável inválida. Use: {', '.join(CAMPOS_MEDIDOS)}"}), 400
    coluna = getattr(Registro, campo)
    q = _consulta().filter(coluna.isnot(None))
    limit = _inteiro("limit", 500, 1, 5000)
    linhas = q.order_by(Registro.registro_tempo.desc()).limit(limit).all()
    linhas.reverse()  # cronológico (mais antigo -> mais novo), pronto para gráfico
    return jsonify({
        "variavel": campo,
        "total": len(linhas),
        "dados": [{"registro_tempo": _fmt_dt(r.registro_tempo), "valor": _num(getattr(r, campo)), "sensor": cod}
                  for r, cod in linhas],
    })


@app.route("/api/mqtt/status", methods=["GET"])
def mqtt_status():
    """Conexão e contadores de recebimento MQTT."""
    with _stats_lock:
        corpo = dict(estatisticas)
    corpo.update({
        "broker": MQTT_BROKER, "porta": MQTT_PORT, "topico": MQTT_TOPIC,
        "fila_pendente": fila_gravacao.qsize(),
        "worker_ativo": bool(_worker_thread and _worker_thread.is_alive()),
    })
    return jsonify(corpo)


# ---- Tratamento de erros da API ----
@app.errorhandler(ValueError)
def erro_parametro(e):
    return jsonify({"erro": str(e)}), 400


@app.errorhandler(SQLAlchemyError)
def erro_banco(e):
    mybd.session.rollback()
    logger.error("Erro de banco na API: %s", e)
    return jsonify({"erro": "Banco de dados indisponível"}), 503


@app.errorhandler(Exception)
def erro_generico(e):
    if isinstance(e, HTTPException):
        return jsonify({"erro": e.description}), e.code
    logger.exception("Erro interno: %s", e)
    return jsonify({"erro": "Erro interno do servidor"}), 500


# ********************* FIM DA API *********************************

if __name__ == '__main__':  # Verifica se este arquivo está sendo executado como o programa principal.
    with app.app_context():  # Cria um contexto de aplicativo Flask para executar a criação do banco de dados.
        # mybd.create_all()  # Chama o método 'create_all' para criar todas as tabelas definidas no modelo do banco de dados.

        start_mqtt()  # Chama a função 'start_mqtt', que presumivelmente inicia um cliente MQTT (protocolo de mensagens para dispositivos).
        port = int(os.environ.get("PORT", 8080))  # Azure define a porta automaticamente
        app.run(host='0.0.0.0', port=port)  # Ouvir em todas as interfaces e usar a porta fornecida pela Azure
