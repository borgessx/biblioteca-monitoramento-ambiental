
import csv
import io

from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, Response
from sqlalchemy import text


def criar_rotas_alertas(banco):

    rotas = Blueprint("rotas_alertas", __name__)

    # =========================================
    # FUNCOES AUXILIARES
    # =========================================

    def consultar(sql, parametros=None):

        resultado = banco.session.execute(
            text(sql),
            parametros or {}
        ).mappings().all()

        return [dict(linha) for linha in resultado]

    def obter_limite(padrao=1000):

        limite = int(
            request.args.get("limite", padrao)
        )

        if limite < 1 or limite > 10000:
            raise ValueError(
                "O limite deve estar entre 1 e 10000."
            )

        return limite

    def filtros_periodo(coluna):

        filtros = []
        parametros = {}

        inicio = request.args.get("inicio")
        fim = request.args.get("fim")

        data_inicio = None
        data_fim = None

        if inicio:

            try:
                data_inicio = datetime.strptime(
                    inicio, "%Y-%m-%d"
                )
            except ValueError:
                raise ValueError(
                    "Data inicial inválida. Utilize AAAA-MM-DD."
                )

            filtros.append(
                f"{coluna} >= :inicio"
            )

            parametros["inicio"] = data_inicio

        if fim:

            try:
                data_fim = datetime.strptime(
                    fim, "%Y-%m-%d"
                )
            except ValueError:
                raise ValueError(
                    "Data final inválida. Utilize AAAA-MM-DD."
                )

            filtros.append(
                f"{coluna} < :fim"
            )

            parametros["fim"] = (
                data_fim + timedelta(days=1)
            )

        if data_inicio and data_fim:

            if data_inicio > data_fim:
                raise ValueError(
                    "A data inicial não pode ser "
                    "maior que a data final."
                )

        return filtros, parametros

    def gerar_csv(dados, colunas, nome):

        arquivo = io.StringIO()

        escritor = csv.DictWriter(
            arquivo,
            fieldnames=colunas,
            delimiter=";",
            extrasaction="ignore"
        )

        escritor.writeheader()
        escritor.writerows(dados)

        return Response(
            "\ufeff" + arquivo.getvalue(),
            content_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition":
                    f'attachment; filename="{nome}"'
            }
        )


    # =========================================
    # CONSULTA DE OCORRENCIAS
    # =========================================

    consulta_ocorrencias = """
        SELECT
            o.id,
            a.nome AS ambiente,
            s.codigo AS sensor,
            i.nome AS indicador,
            i.campo,
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

    def buscar_ocorrencias(status_fixo=None):

        filtros, parametros = filtros_periodo(
            "o.data_abertura"
        )

        status = (
            status_fixo or
            request.args.get("status")
        )

        ambiente = request.args.get("ambiente")
        sensor = request.args.get("sensor")
        indicador = request.args.get("indicador")

        if status:

            status = status.upper()

            if status not in (
                "ABERTA", "ENCERRADA"
            ):
                raise ValueError(
                    "Status de ocorrência inválido."
                )

            filtros.append("o.status = :status")
            parametros["status"] = status

        if ambiente:
            filtros.append("a.nome = :ambiente")
            parametros["ambiente"] = ambiente

        if sensor:
            filtros.append("s.codigo = :sensor")
            parametros["sensor"] = sensor

        if indicador:
            filtros.append("""
                (i.campo = :indicador
                 OR i.nome = :indicador)
            """)

            parametros["indicador"] = indicador

        sql = consulta_ocorrencias

        if filtros:
            sql += " WHERE " + " AND ".join(filtros)

        sql += " ORDER BY o.id DESC LIMIT :limite"

        parametros["limite"] = obter_limite()

        return consultar(sql, parametros)

    @rotas.route("/api/ocorrencias", methods=["GET"])
    def listar_ocorrencias():

        dados = buscar_ocorrencias()

        return jsonify({
            "total": len(dados),
            "ocorrencias": dados
        })

    @rotas.route(
        "/api/ocorrencias/abertas",
        methods=["GET"]
    )
    def listar_abertas():

        dados = buscar_ocorrencias("ABERTA")

        return jsonify({
            "total": len(dados),
            "ocorrencias": dados
        })

    @rotas.route(
        "/api/ocorrencias/encerradas",
        methods=["GET"]
    )
    def listar_encerradas():

        dados = buscar_ocorrencias("ENCERRADA")

        return jsonify({
            "total": len(dados),
            "ocorrencias": dados
        })

    # =========================================
    # NOTIFICACOES
    # =========================================

    @rotas.route("/api/notificacoes", methods=["GET"])
    def listar_notificacoes():

        sql = """
            SELECT
                n.id,
                n.id_ocorrencia,
                i.nome AS indicador,
                n.status_envio,
                n.data_envio,
                n.tentativas,
                n.proxima_tentativa
            FROM notificacao n
            INNER JOIN ocorrencia o
                ON n.id_ocorrencia = o.id
            INNER JOIN limite l
                ON o.id_limite = l.id
            INNER JOIN indicador i
                ON l.id_indicador = i.id
        """

        filtros, parametros = filtros_periodo(
            "n.data_envio"
        )

        status = request.args.get("status")
        indicador = request.args.get("indicador")

        if status:

            status = status.upper()

            if status not in (
                "PENDENTE",
                "ENVIANDO",
                "ENVIADO",
                "ERRO"
            ):
                raise ValueError(
                    "Status de notificação inválido."
                )

            filtros.append(
                "n.status_envio = :status"
            )

            parametros["status"] = status

        if indicador:

            filtros.append("""
                (i.campo = :indicador
                 OR i.nome = :indicador)
            """)

            parametros["indicador"] = indicador

        if filtros:
            sql += " WHERE " + " AND ".join(filtros)

        sql += " ORDER BY n.id DESC LIMIT :limite"

        parametros["limite"] = obter_limite()

        dados = consultar(sql, parametros)

        return jsonify({
            "total": len(dados),
            "notificacoes": dados
        })

    # =========================================
    # INDICADORES
    # =========================================

    @rotas.route("/api/indicadores", methods=["GET"])
    def listar_indicadores():

        dados = consultar("""
            SELECT
                id,
                nome,
                campo,
                unidade,
                descricao
            FROM indicador
            WHERE campo IN (
                'temperature',
                'humidity',
                'CO2',
                'particula1',
                'particula2'
            )
            ORDER BY id
        """)

        return jsonify({
            "total": len(dados),
            "indicadores": dados
        })

    # =========================================
    # LIMITES AMBIENTAIS
    # =========================================

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
            WHERE i.campo IN (
                'temperature',
                'humidity',
                'CO2',
                'particula1',
                'particula2'
            )
            ORDER BY l.id
        """)

        return jsonify({
            "total": len(dados),
            "limites": dados
        })

    # =========================================
    # AMBIENTES
    # =========================================

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

    # =========================================
    # KPIS
    # =========================================

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
                 FROM ocorrencia)
                 AS total_ocorrencias,

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
                 WHERE status_envio = 'ENVIANDO')
                 AS emails_enviando,

                (SELECT COUNT(*)
                 FROM notificacao
                 WHERE status_envio = 'ERRO')
                 AS emails_com_erro
        """)

        return jsonify(dados[0])

    # =========================================
    # EXPORTACAO DE MEDICOES EM CSV
    # =========================================

    @rotas.route(
        "/api/exportar/medicoes",
        methods=["GET"]
    )
    def exportar_medicoes():

        sql = """
            SELECT
                m.id,
                a.nome AS ambiente,
                s.codigo AS sensor,
                m.temperature,
                m.humidity,
                m.CO2,
                m.particula1,
                m.particula2,
                m.registro_tempo
            FROM medicao m
            INNER JOIN sensor s
                ON m.id_sensor = s.id
            INNER JOIN ambiente a
                ON s.id_ambiente = a.id
        """

        filtros, parametros = filtros_periodo(
            "m.registro_tempo"
        )

        sensor = request.args.get("sensor")
        ambiente = request.args.get("ambiente")

        if sensor:
            filtros.append("s.codigo = :sensor")
            parametros["sensor"] = sensor

        if ambiente:
            filtros.append("a.nome = :ambiente")
            parametros["ambiente"] = ambiente

        if filtros:
            sql += " WHERE " + " AND ".join(filtros)

        sql += """
            ORDER BY m.registro_tempo DESC
            LIMIT :limite
        """

        parametros["limite"] = obter_limite(10000)

        dados = consultar(sql, parametros)

        colunas = [
            "id",
            "ambiente",
            "sensor",
            "temperature",
            "humidity",
            "CO2",
            "particula1",
            "particula2",
            "registro_tempo"
        ]

        return gerar_csv(
            dados,
            colunas,
            "medicoes_ambientais.csv"
        )

    # =========================================
    # EXPORTACAO DE OCORRENCIAS EM CSV
    # =========================================

    @rotas.route(
        "/api/exportar/ocorrencias",
        methods=["GET"]
    )
    def exportar_ocorrencias():

        dados = buscar_ocorrencias()

        colunas = [
            "id",
            "ambiente",
            "sensor",
            "indicador",
            "campo",
            "unidade",
            "valor_registrado",
            "valor_minimo",
            "valor_maximo",
            "gravidade",
            "status",
            "data_abertura",
            "data_encerramento"
        ]

        return gerar_csv(
            dados,
            colunas,
            "ocorrencias_ambientais.csv"
        )

    return rotas
