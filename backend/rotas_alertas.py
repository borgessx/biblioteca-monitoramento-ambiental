
from flask import Blueprint, jsonify
from sqlalchemy import text


def criar_rotas_alertas(banco):

    rotas = Blueprint("rotas_alertas", __name__)

    def consultar(sql, parametros=None):

        resultado = banco.session.execute(
            text(sql),
            parametros or {}
        ).mappings().all()

        return [dict(linha) for linha in resultado]

    consulta_ocorrencias = """
        SELECT
            o.id,
            a.nome AS ambiente,
            s.codigo AS sensor,
            i.nome AS indicador,
            i.unidade,
            o.valor_registrado,
            l.valor_minimo,
            l.valor_maximo,
            l.gravidade,
            o.status,
            o.data_abertura,
            o.data_encerramento
        FROM ocorrencia o
        INNER JOIN medicao m
            ON o.id_medicao = m.id
        INNER JOIN sensor s
            ON m.id_sensor = s.id
        INNER JOIN ambiente a
            ON s.id_ambiente = a.id
        INNER JOIN limite l
            ON o.id_limite = l.id
        INNER JOIN indicador i
            ON l.id_indicador = i.id
    """

    # Todas as ocorrencias
    @rotas.route("/api/ocorrencias", methods=["GET"])
    def listar_ocorrencias():

        dados = consultar(
            consulta_ocorrencias +
            " ORDER BY o.id DESC"
        )

        return jsonify({
            "total": len(dados),
            "ocorrencias": dados
        })

    # Ocorrencias abertas
    @rotas.route("/api/ocorrencias/abertas", methods=["GET"])
    def listar_abertas():

        dados = consultar(
            consulta_ocorrencias +
            " WHERE o.status = 'ABERTA'"
            " ORDER BY o.id DESC"
        )

        return jsonify({
            "total": len(dados),
            "ocorrencias": dados
        })

    # Ocorrencias encerradas
    @rotas.route("/api/ocorrencias/encerradas", methods=["GET"])
    def listar_encerradas():

        dados = consultar(
            consulta_ocorrencias +
            " WHERE o.status = 'ENCERRADA'"
            " ORDER BY o.id DESC"
        )

        return jsonify({
            "total": len(dados),
            "ocorrencias": dados
        })

    # Historico de notificacoes
    @rotas.route("/api/notificacoes", methods=["GET"])
    def listar_notificacoes():

        dados = consultar("""
            SELECT
                n.id,
                n.id_ocorrencia,
                i.nome AS indicador,
                n.status_envio,
                n.data_envio
            FROM notificacao n
            INNER JOIN ocorrencia o
                ON n.id_ocorrencia = o.id
            INNER JOIN limite l
                ON o.id_limite = l.id
            INNER JOIN indicador i
                ON l.id_indicador = i.id
            ORDER BY n.id DESC
        """)

        return jsonify({
            "total": len(dados),
            "notificacoes": dados
        })

    # Indicadores cadastrados
    @rotas.route("/api/indicadores", methods=["GET"])
    def listar_indicadores():

        dados = consultar("""
            SELECT id, nome, campo, unidade, descricao
            FROM indicador
            ORDER BY id
        """)

        return jsonify({
            "total": len(dados),
            "indicadores": dados
        })

    # Limites ambientais
    @rotas.route("/api/limites", methods=["GET"])
    def listar_limites():

        dados = consultar("""
            SELECT
                l.id,
                a.nome AS ambiente,
                i.nome AS indicador,
                i.campo,
                i.unidade,
                l.valor_minimo,
                l.valor_maximo,
                l.gravidade,
                l.ativo
            FROM limite l
            INNER JOIN ambiente a
                ON l.id_ambiente = a.id
            INNER JOIN indicador i
                ON l.id_indicador = i.id
            ORDER BY l.id
        """)

        return jsonify({
            "total": len(dados),
            "limites": dados
        })

    # Ambientes monitorados
    @rotas.route("/api/ambientes", methods=["GET"])
    def listar_ambientes():

        dados = consultar("""
            SELECT id, nome, descricao, ativo
            FROM ambiente
            ORDER BY id
        """)

        return jsonify({
            "total": len(dados),
            "ambientes": dados
        })

    # KPIs do dashboard
    @rotas.route("/api/kpis", methods=["GET"])
    def listar_kpis():

        dados = consultar("""
            SELECT
                (SELECT COUNT(*)
                 FROM medicao) AS total_medicoes,

                (SELECT COUNT(*)
                 FROM sensor) AS total_sensores,

                (SELECT COUNT(*)
                 FROM ambiente) AS total_ambientes,

                (SELECT COUNT(*)
                 FROM ocorrencia) AS total_ocorrencias,

                (SELECT COUNT(*)
                 FROM ocorrencia
                 WHERE status = 'ABERTA')
                 AS ocorrencias_abertas,

                (SELECT COUNT(*)
                 FROM ocorrencia
                 WHERE status = 'ENCERRADA')
                 AS ocorrencias_encerradas,

                (SELECT COUNT(*)
                 FROM notificacao
                 WHERE status_envio = 'ENVIADO')
                 AS emails_enviados,

                (SELECT COUNT(*)
                 FROM notificacao
                 WHERE status_envio = 'PENDENTE')
                 AS emails_pendentes,

                (SELECT COUNT(*)
                 FROM notificacao
                 WHERE status_envio = 'ERRO')
                 AS emails_com_erro
        """)

        return jsonify(dados[0])

    return rotas
