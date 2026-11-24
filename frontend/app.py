
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template, request
import requests

app = Flask(__name__)

# Backend no outro computador.
# Por enquanto, mantemos este endereço.
# Se estiver inacessível, o frontend continua funcionando.
API_BACKEND = "http://127.0.0.1:8080"

LATITUDE = -23.6229
LONGITUDE = -46.5714
FUSO = "America/Sao_Paulo"

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_HISTORICO = (
    "https://archive-api.open-meteo.com/v1/archive"
)

ENDPOINTS = {
    "health": "/health",
    "ultima": "/api/leituras/ultima",
    "leituras": "/api/leituras",
    "kpis": "/api/kpis",
    "limites": "/api/limites",
    "ambientes": "/api/ambientes",
}


@app.route("/")
def inicio():
    return render_template("index.html")


@app.get("/dados/<nome>")
def dados_backend(nome):
    if nome not in ENDPOINTS:
        return jsonify({
            "erro": "Endpoint desconhecido"
        }), 404

    parametros = {}

    if nome == "leituras":
        parametros = {
            "limite": 10000,
            "ordem": "desc"
        }

    try:
        resposta = requests.get(
            API_BACKEND + ENDPOINTS[nome],
            params=parametros,
            timeout=3
        )

        if not resposta.ok:
            return jsonify({
                "disponivel": False,
                "erro": "Backend indisponivel",
                "status_backend": resposta.status_code
            }), 503

        return jsonify(resposta.json())

    except (requests.RequestException, ValueError):
        return jsonify({
            "disponivel": False,
            "erro": "Backend nao conectado neste computador"
        }), 503


@app.get("/dados/clima-externo")
def clima_externo():
    agora = datetime.now(ZoneInfo(FUSO))
    hoje = agora.date()

    try:
        dias = int(request.args.get("dias", 1))
    except ValueError:
        return jsonify({"erro": "Periodo invalido"}), 400

    if dias not in (1, 3, 7):
        return jsonify({
            "erro": "Escolha 1, 3 ou 7 dias"
        }), 400

    inicio = hoje - timedelta(days=dias - 1)

    parametros = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": (
            "temperature_2m,"
            "relative_humidity_2m"
        ),
        "timezone": FUSO,
        "start_date": inicio.isoformat(),
        "end_date": hoje.isoformat(),
    }

    try:
        resposta = requests.get(
            OPEN_METEO,
            params=parametros,
            timeout=20
        )

        resposta.raise_for_status()
        dados = resposta.json()

        if dados.get("error"):
            return jsonify({
                "erro": dados.get("reason", "Erro Open-Meteo")
            }), 502

        hourly = dados.get("hourly", {})

        horarios = hourly.get("time", [])
        temperaturas = hourly.get("temperature_2m", [])
        umidades = hourly.get("relative_humidity_2m", [])

        registros = []

        for i, horario in enumerate(horarios):
            data_hora = datetime.fromisoformat(
                horario
            ).replace(tzinfo=ZoneInfo(FUSO))

            # Nao apresenta previsoes futuras
            # como observacoes atuais.
            if data_hora > agora:
                continue

            registros.append({
                "horario": horario,
                "temperatura": (
                    temperaturas[i]
                    if i < len(temperaturas)
                    else None
                ),
                "umidade": (
                    umidades[i]
                    if i < len(umidades)
                    else None
                ),
                "origem": "open_meteo_modelo"
            })

        return jsonify({
            "cidade": "Sao Caetano do Sul",
            "estado": "SP",
            "timezone": FUSO,
            "fonte": "Open-Meteo Forecast API",
            "tipo": "dados_meteorologicos_modelados",
            "horas": registros,
            "total": len(registros)
        })

    except (requests.RequestException, ValueError) as erro:
        app.logger.warning(
            "Falha na Open-Meteo: %s",
            erro
        )

        return jsonify({
            "erro": "Nao foi possivel consultar a Open-Meteo"
        }), 502


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
