
import os
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from dotenv import load_dotenv
from alerta_email import enviar_email

load_dotenv()

logger = logging.getLogger("monitoramento")


def agora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def verificar_valor(valor, minimo, maximo):

    if valor is None:
        return False

    if minimo is not None and valor < minimo:
        return True

    if maximo is not None and valor > maximo:
        return True

    return False


def consultar_limites(banco, id_ambiente):

    consulta = text("""
        SELECT
            l.id AS id_limite,
            i.nome AS indicador,
            i.campo,
            i.unidade,
            l.valor_minimo,
            l.valor_maximo,
            l.gravidade,
            a.nome AS ambiente
        FROM limite l
        INNER JOIN indicador i
            ON l.id_indicador = i.id
        INNER JOIN ambiente a
            ON l.id_ambiente = a.id
        WHERE l.id_ambiente = :ambiente
        AND l.ativo = TRUE
    """)

    return banco.session.execute(
        consulta,
        {"ambiente": id_ambiente}
    ).mappings().all()


def verificar_limites(banco, id_ambiente, valores):

    alertas = []

    for limite in consultar_limites(banco, id_ambiente):

        valor = valores.get(limite["campo"])

        if verificar_valor(
            valor,
            limite["valor_minimo"],
            limite["valor_maximo"]
        ):
            alertas.append(dict(
                limite,
                valor=valor,
                minimo=limite["valor_minimo"],
                maximo=limite["valor_maximo"]
            ))

    return alertas


def processar_ocorrencias(
    banco,
    id_ambiente,
    id_sensor,
    codigo,
    id_medicao,
    valores
):

    destinatario = os.getenv("EMAIL_DESTINATARIO")

    # Bloqueio exclusivo para MySQL e MariaDB
    if banco.engine.dialect.name in ("mysql", "mariadb"):

        banco.session.execute(
            text("""
                SELECT id FROM sensor
                WHERE id = :id
                FOR UPDATE
            """),
            {"id": id_sensor}
        )

    limites = consultar_limites(banco, id_ambiente)

    for limite in limites:

        valor = valores.get(limite["campo"])

        if valor is None:
            continue

        aberta = banco.session.execute(
            text("""
                SELECT o.id
                FROM ocorrencia o
                INNER JOIN medicao m
                    ON m.id = o.id_medicao
                WHERE m.id_sensor = :sensor
                AND o.id_limite = :limite
                AND o.status = 'ABERTA'
                LIMIT 1
            """),
            {
                "sensor": id_sensor,
                "limite": limite["id_limite"]
            }
        ).scalar()

        minimo = limite["valor_minimo"]
        maximo = limite["valor_maximo"]

        fora_limite = verificar_valor(
            valor, minimo, maximo
        )

        if fora_limite:

            # Evita ocorrencias duplicadas
            if aberta is not None:
                continue

            resultado = banco.session.execute(
                text("""
                    INSERT INTO ocorrencia (
                        id_medicao,
                        id_limite,
                        valor_registrado,
                        status,
                        data_abertura
                    )
                    VALUES (
                        :medicao,
                        :limite,
                        :valor,
                        'ABERTA',
                        :data
                    )
                """),
                {
                    "medicao": id_medicao,
                    "limite": limite["id_limite"],
                    "valor": valor,
                    "data": agora()
                }
            )

            id_ocorrencia = resultado.lastrowid

            unidade = limite["unidade"] or ""

            mensagem = (
                "ALERTA AMBIENTAL\n\n"
                f"Ambiente: {limite['ambiente']}\n"
                f"Sensor: {codigo}\n"
                f"Indicador: {limite['indicador']}\n"
                f"Valor registrado: {valor} {unidade}\n"
                f"Limites: {minimo} a {maximo} {unidade}\n\n"
                "Solicitamos a verificacao do ambiente.\n"
                "Projeto Integrador II - SENAI"
            )

            if destinatario:

                banco.session.execute(
                    text("""
                        INSERT INTO notificacao (
                            id_ocorrencia,
                            destinatario,
                            mensagem,
                            status_envio
                        )
                        VALUES (
                            :ocorrencia,
                            :destinatario,
                            :mensagem,
                            'PENDENTE'
                        )
                    """),
                    {
                        "ocorrencia": id_ocorrencia,
                        "destinatario": destinatario,
                        "mensagem": mensagem[:500]
                    }
                )

            else:
                logger.warning(
                    "EMAIL_DESTINATARIO nao configurado"
                )

            logger.warning(
                "Ocorrencia aberta: %s / %s",
                codigo,
                limite["indicador"]
            )

        elif aberta is not None:

            banco.session.execute(
                text("""
                    UPDATE ocorrencia
                    SET status = 'ENCERRADA',
                        data_encerramento = :data
                    WHERE id = :id
                """),
                {
                    "data": agora(),
                    "id": aberta
                }
            )

            logger.info(
                "Ocorrencia encerrada: %s",
                aberta
            )

    banco.session.commit()



def enviar_pendente(banco):

    MAX_TENTATIVAS = 3

    notificacao = banco.session.execute(
        text("""
            SELECT
                id,
                destinatario,
                mensagem,
                tentativas
            FROM notificacao
            WHERE status_envio = 'PENDENTE'
            AND tentativas < :maximo
            AND (
                proxima_tentativa IS NULL
                OR proxima_tentativa <= :agora
            )
            ORDER BY id
            LIMIT 1
        """),
        {
            "maximo": MAX_TENTATIVAS,
            "agora": agora()
        }
    ).mappings().first()

    if notificacao is None:
        banco.session.rollback()
        return

    notificacao = dict(notificacao)

    tentativa = notificacao["tentativas"] + 1

    # Reserva a notificacao para envio
    resultado = banco.session.execute(
        text("""
            UPDATE notificacao
            SET status_envio = 'ENVIANDO',
                tentativas = tentativas + 1,
                proxima_tentativa = NULL
            WHERE id = :id
            AND status_envio = 'PENDENTE'
            AND tentativas = :anterior
        """),
        {
            "id": notificacao["id"],
            "anterior": notificacao["tentativas"]
        }
    )

    banco.session.commit()

    if resultado.rowcount != 1:
        return

    try:

        enviar_email(
            notificacao["destinatario"],
            "ALERTA - Monitoramento Ambiental",
            notificacao["mensagem"]
        )

        status = "ENVIADO"
        data_envio = agora()
        proxima_tentativa = None
        ultimo_erro = None

        logger.info(
            "Notificacao %s enviada na tentativa %s",
            notificacao["id"],
            tentativa
        )

    except Exception as erro:

        logger.exception(
            "Falha no envio da notificacao %s",
            notificacao["id"]
        )

        data_envio = None
        ultimo_erro = type(erro).__name__

        if tentativa >= MAX_TENTATIVAS:

            status = "ERRO"
            proxima_tentativa = None

            logger.error(
                "Notificacao %s atingiu o limite de tentativas",
                notificacao["id"]
            )

        else:

            status = "PENDENTE"

            intervalo = 60 * tentativa

            proxima_tentativa = (
                agora() + timedelta(seconds=intervalo)
            )

            logger.warning(
                "Notificacao %s sera reenviada em %s segundos",
                notificacao["id"],
                intervalo
            )

    banco.session.execute(
        text("""
            UPDATE notificacao
            SET status_envio = :status,
                data_envio = :data_envio,
                proxima_tentativa = :proxima,
                ultimo_erro = :erro
            WHERE id = :id
            AND status_envio = 'ENVIANDO'
            AND tentativas = :tentativa
        """),
        {
            "status": status,
            "data_envio": data_envio,
            "proxima": proxima_tentativa,
            "erro": ultimo_erro,
            "id": notificacao["id"],
            "tentativa": tentativa
        }
    )

    banco.session.commit()



def worker_notificacoes(app, banco, parar):

    while not parar.is_set():

        with app.app_context():

            try:
                enviar_pendente(banco)

            except Exception:
                banco.session.rollback()
                logger.exception(
                    "Erro no worker de notificacoes"
                )

        parar.wait(2)
