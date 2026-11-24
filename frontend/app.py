
from flask import Flask, jsonify, render_template, request
import requests

app = Flask(__name__)

API_BACKEND = "http://127.0.0.1:8080"

ENDPOINTS = {
    "health": "/health",
    "ultima": "/api/leituras/ultima",
    "leituras": "/api/leituras",
    "kpis": "/api/kpis",
    "limites": "/api/limites",
    "ambientes": "/api/ambientes",
    "ocorrencias": "/api/ocorrencias/abertas",
}


@app.get("/")
def inicio():
    return render_template("index.html")


@app.get("/dados/<nome>")
def consultar_dados(nome):
    if nome not in ENDPOINTS:
        return jsonify({"erro": "Consulta inexistente"}), 404

    parametros = {}

    if nome == "leituras":
        # Amplia a consulta para montar o histórico semanal.
        parametros["limite"] = 10000
        parametros["ordem"] = "desc"

        for campo in ("inicio", "fim", "sensor"):
            valor = request.args.get(campo)
            if valor:
                parametros[campo] = valor

    try:
        resposta = requests.get(
            API_BACKEND + ENDPOINTS[nome],
            params=parametros,
            timeout=20
        )

        try:
            dados = resposta.json()
        except ValueError:
            return jsonify({
                "erro": "Backend devolveu resposta nao JSON"
            }), 502

        return jsonify(dados), resposta.status_code

    except requests.exceptions.RequestException:
        app.logger.exception(
            "Falha ao consultar %s", nome
        )

        return jsonify({
            "erro": "Nao foi possivel consultar o backend"
        }), 502


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
