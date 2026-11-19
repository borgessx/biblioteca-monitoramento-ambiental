
import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["EMAIL_DESTINATARIO"] = "teste@example.invalid"

import unittest
import tempfile
import json

from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

import mqtt as m
import alertas as a


class Teste(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        with m.app.app_context():
            m.mybd.session.remove()
            m.mybd.engine.dispose()
        super().tearDownClass()
    def setUp(self):
        
        self.ctx = m.app.app_context()
        self.ctx.push()
        self.addCleanup(self.ctx.pop)

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.patch = patch.object(
            m,
            "ARQUIVO_REJEITADAS",
            str(
                Path(self.temp.name) /
                "rejeitadas.jsonl"
            )
        )

        self.patch.start()
        self.addCleanup(self.patch.stop)

        m._parar.clear()

        for tabela in (
            "notificacao",
            "ocorrencia",
            "limite",
            "indicador",
            "ambiente"
        ):

            m.mybd.session.execute(
                text(f"DROP TABLE IF EXISTS {tabela}")
            )

        m.mybd.session.commit()

        m.mybd.drop_all()
        m.mybd.create_all()

        comandos = [

            """
            CREATE TABLE ambiente (
                id INTEGER PRIMARY KEY,
                nome TEXT
            )
            """,

            """
            CREATE TABLE indicador (
                id INTEGER PRIMARY KEY,
                nome TEXT,
                campo TEXT,
                unidade TEXT
            )
            """,

            """
            CREATE TABLE limite (
                id INTEGER PRIMARY KEY,
                id_ambiente INTEGER,
                id_indicador INTEGER,
                valor_minimo NUMERIC,
                valor_maximo NUMERIC,
                gravidade TEXT,
                ativo BOOLEAN
            )
            """,

            """
            CREATE TABLE ocorrencia (
                id INTEGER PRIMARY KEY,
                id_medicao INTEGER,
                id_limite INTEGER,
                valor_registrado NUMERIC,
                status TEXT,
                data_abertura DATETIME,
                data_encerramento DATETIME
            )
            """,

            """
            CREATE TABLE notificacao (
                id INTEGER PRIMARY KEY,
                id_ocorrencia INTEGER,
                destinatario TEXT,
                mensagem TEXT,
                status_envio TEXT,
                data_envio DATETIME,
                tentativas INTEGER NOT NULL DEFAULT 0,
                proxima_tentativa DATETIME,
                ultimo_erro TEXT
            )
            """,

            """
            INSERT INTO ambiente
            VALUES (1, 'Biblioteca')
            """,

            """
            INSERT INTO indicador VALUES
            (1, 'Temperatura', 'temperature', 'C'),
            (2, 'Umidade', 'humidity', '%'),
            (3, 'CO2', 'CO2', 'ppm')
            """,

            """
            INSERT INTO limite VALUES
            (1, 1, 1, 18, 26, 'ALERTA', 1),
            (2, 1, 2, 40, 60, 'ALERTA', 1),
            (3, 1, 3, 0, 1000, 'ALERTA', 1)
            """
        ]

        for comando in comandos:
            m.mybd.session.execute(text(comando))

        sensor = m.Sensor(
            id=1,
            id_ambiente=1,
            nome="Sensor Teste",
            codigo=m.SENSOR_CODIGO_PADRAO
        )

        m.mybd.session.add(sensor)
        m.mybd.session.commit()

        self.ts = int(
            datetime.now(timezone.utc).timestamp()
        )

    def dados(self, **kwargs):

        dados = {
            "temperature": 22,
            "pressure": 92954.63,
            "altitude": 776.5,
            "humidity": 50,
            "CO2": 650,
            "particula1": 12,
            "particula2": 8,
            "timestamp": self.ts
        }

        dados.update(kwargs)

        return dados

    def receber(self, dados, topico=None):

        if isinstance(dados, bytes):
            payload = dados
        else:
            payload = json.dumps(dados).encode()

        mensagem = SimpleNamespace(
            payload=payload,
            topic=topico or m.MQTT_TOPIC
        )

        m.on_message(None, None, mensagem)

        while not m.fila_gravacao.empty():

            item = m.fila_gravacao.get_nowait()

            try:
                m._gravar_com_retry(item)
            finally:
                m.fila_gravacao.task_done()

        m.mybd.session.expire_all()

    def linhas(self):
        return m.Registro.query.all()

    def sql(self, consulta):
        return m.mybd.session.execute(
            text(consulta)
        ).scalar()

    def rejeitadas(self):
        return Path(
            m.ARQUIVO_REJEITADAS
        ).read_text(encoding="utf-8")

    def test_mensagem_valida(self):

        self.receber(self.dados())

        registro = self.linhas()[0]

        self.assertEqual(registro.id_sensor, 1)
        self.assertEqual(float(registro.temperature), 22)

    def test_duplicada_ignorada(self):

        dados = self.dados()

        self.receber(dados)
        self.receber(dados)

        self.assertEqual(len(self.linhas()), 1)

    def test_json_invalido(self):

        self.receber(b"{quebrado")

        self.assertIn(
            "json inválido",
            self.rejeitadas()
        )

        self.assertFalse(self.linhas())

    def test_valores_invalidos(self):

        self.receber({"temperature": 20})

        self.receber(
            self.dados(temperature="abc")
        )

        self.receber(
            self.dados(CO2=float("nan"))
        )

        self.receber(
            self.dados(timestamp=0)
        )

        self.assertFalse(self.linhas())

    def test_sensor_nao_cadastrado(self):

        with patch.dict(
            m.TOPICO_PARA_SENSOR,
            {"outro/topico": "NAO_EXISTE"}
        ):

            self.receber(
                self.dados(),
                "outro/topico"
            )

        self.assertIn(
            "não cadastrado",
            self.rejeitadas()
        )

    def test_timestamp_em_ms(self):

        self.receber(
            self.dados(timestamp=self.ts * 1000)
        )

        esperado = datetime.fromtimestamp(
            self.ts,
            timezone.utc
        ).replace(tzinfo=None)

        self.assertEqual(
            self.linhas()[0].registro_tempo,
            esperado
        )

    def test_valor_ausente(self):

        dados = self.dados()
        del dados["CO2"]

        self.receber(dados)

        self.assertIsNone(
            self.linhas()[0].CO2
        )

    def test_endpoints(self):

        self.receber(self.dados())

        cliente = m.app.test_client()

        self.assertEqual(
            cliente.get("/health").status_code,
            200
        )

        self.assertEqual(
            cliente.get("/api/leituras").json["total"],
            1
        )

        self.assertEqual(
            cliente.get(
                "/api/leituras/ultima"
            ).json["temperature"],
            22
        )

        self.assertEqual(
            cliente.get("/api/sensores").status_code,
            200
        )

    def test_banco_cai_e_volta(self):

        commit_original = m.mybd.session.commit
        chamadas = [0]

        def commit():

            chamadas[0] += 1

            if chamadas[0] == 1:
                raise OperationalError(
                    "INSERT",
                    {},
                    Exception("Banco fora")
                )

            return commit_original()

        with patch.object(
            m.mybd.session,
            "commit",
            side_effect=commit
        ), patch.object(
            m._parar,
            "wait",
            return_value=False
        ):

            self.receber(self.dados())

        self.assertEqual(len(self.linhas()), 1)

    def test_ciclo_alertas(self):

        with patch.object(
            a,
            "enviar_email",
            return_value={"id": "simulado"}
        ) as envio:

            self.receber(
                self.dados(
                    temperature=32,
                    humidity=78,
                    CO2=1500
                )
            )

            self.assertEqual(
                self.sql(
                    "SELECT COUNT(*) FROM ocorrencia"
                ),
                3
            )

            # Nao deve duplicar ocorrencias
            self.receber(
                self.dados(
                    temperature=32,
                    humidity=78,
                    CO2=1500,
                    timestamp=self.ts + 1
                )
            )

            self.assertEqual(
                self.sql(
                    "SELECT COUNT(*) FROM ocorrencia"
                ),
                3
            )

            # Simula o envio dos tres emails
            for _ in range(3):
                a.enviar_pendente(m.mybd)

            self.assertEqual(envio.call_count, 3)

            self.assertEqual(
                self.sql("""
                    SELECT COUNT(*) FROM notificacao
                    WHERE status_envio = 'ENVIADO'
                """),
                3
            )

            # Normaliza os indicadores
            self.receber(
                self.dados(timestamp=self.ts + 2)
            )

            self.assertEqual(
                self.sql("""
                    SELECT COUNT(*) FROM ocorrencia
                    WHERE status = 'ENCERRADA'
                """),
                3
            )

            # Gera novos alertas
            self.receber(
                self.dados(
                    temperature=32,
                    humidity=78,
                    CO2=1500,
                    timestamp=self.ts + 3
                )
            )

            self.assertEqual(
                self.sql("""
                    SELECT COUNT(*) FROM ocorrencia
                    WHERE status = 'ABERTA'
                """),
                3
            )

            self.assertEqual(
                self.sql(
                    "SELECT COUNT(*) FROM notificacao"
                ),
                6
            )


    def test_falha_email(self):

        self.receber(
            self.dados(temperature=32)
        )

        with patch.object(
            a,
            "enviar_email",
            side_effect=RuntimeError("Falha simulada")
        ) as envio:

            for tentativa in range(1, 4):

                a.enviar_pendente(m.mybd)

                self.assertEqual(
                    self.sql(
                        "SELECT tentativas FROM notificacao"
                    ),
                    tentativa
                )

                if tentativa < 3:

                    self.assertEqual(
                        self.sql(
                            "SELECT status_envio FROM notificacao"
                        ),
                        "PENDENTE"
                    )

                    # Confirma que nao reenvia antes do horario
                    a.enviar_pendente(m.mybd)

                    self.assertEqual(
                        envio.call_count,
                        tentativa
                    )

                    # Libera a proxima tentativa no teste
                    m.mybd.session.execute(
                        text("""
                            UPDATE notificacao
                            SET proxima_tentativa = NULL
                        """)
                    )

                    m.mybd.session.commit()

            self.assertEqual(envio.call_count, 3)

            self.assertEqual(
                self.sql(
                    "SELECT status_envio FROM notificacao"
                ),
                "ERRO"
            )

            # Confirma que nao existe quarta tentativa
            a.enviar_pendente(m.mybd)

            self.assertEqual(envio.call_count, 3)



if __name__ == "__main__":
    unittest.main(verbosity=2)
