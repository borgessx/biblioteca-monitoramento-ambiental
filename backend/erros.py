
import logging

from flask import jsonify
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException


logger = logging.getLogger("monitoramento")


def registrar_erros(app, banco):

    @app.errorhandler(400)
    def requisicao_invalida(erro):

        return jsonify({
            "status": 400,
            "erro": "Requisicao invalida",
            "mensagem": erro.description
        }), 400

    @app.errorhandler(404)
    def nao_encontrado(erro):

        return jsonify({
            "status": 404,
            "erro": "Recurso nao encontrado",
            "mensagem": "O recurso solicitado nao existe."
        }), 404

    @app.errorhandler(405)
    def metodo_nao_permitido(erro):

        resposta = jsonify({
            "status": 405,
            "erro": "Metodo nao permitido",
            "mensagem": "Metodo HTTP nao autorizado."
        })

        resposta.status_code = 405

        if erro.valid_methods:
            resposta.headers["Allow"] = ", ".join(
                erro.valid_methods
            )

        return resposta

    @app.errorhandler(SQLAlchemyError)
    def erro_banco(erro):

        banco.session.rollback()

        logger.exception(
            "Erro na operacao com o banco de dados"
        )

        return jsonify({
            "status": 500,
            "erro": "Erro no banco de dados",
            "mensagem": "Nao foi possivel realizar a operacao."
        }), 500

    @app.errorhandler(ValueError)
    def erro_valor(erro):

        return jsonify({
            "status": 400,
            "erro": "Valor invalido",
            "mensagem": str(erro)
        }), 400

    @app.errorhandler(Exception)
    def erro_inesperado(erro):

        if isinstance(erro, HTTPException):

            resposta = erro.get_response()

            resposta.set_data(app.json.dumps({
                "status": erro.code,
                "erro": erro.name,
                "mensagem": erro.description
            }))

            resposta.content_type = "application/json"

            return resposta

        banco.session.rollback()

        logger.exception(
            "Erro inesperado na API"
        )

        return jsonify({
            "status": 500,
            "erro": "Erro interno",
            "mensagem": "Ocorreu um erro inesperado no servidor."
        }), 500
