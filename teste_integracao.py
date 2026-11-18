"""Testes sem broker real: chama on_message com mensagens simuladas e usa SQLite temporário.
Execute: python teste_integracao.py"""
import json, os, tempfile, time, unittest
from datetime import datetime, timezone
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/teste.db"
os.environ["REJEITADAS_ARQUIVO"] = f"{_tmp}/rejeitadas.jsonl"

import mqtt as m  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402


class Msg:
    def __init__(self, payload, topic=m.MQTT_TOPIC):
        self.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.topic = topic


def ts(ano=2026, mes=11, dia=17, h=12, mi=0, s=0):
    return int(datetime(ano, mes, dia, h, mi, s, tzinfo=timezone.utc).timestamp())


def payload(t=ts(), **extra):
    d = {"temperature": 25.5, "pressure": 1013.2, "altitude": 760.0, "humidity": 60.1,
         "CO2": 612, "particula1": 12.3, "particula2": 8.7, "timestamp": t}
    d.update(extra)
    return d


class Teste(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with m.app.app_context():
            m.mybd.create_all()
            m.mybd.session.add(m.Sensor(id_ambiente=1, nome="IoT padrão", codigo="IOT_PADRAO"))
            m.mybd.session.commit()
        m.iniciar_worker()
        cls.c = m.app.test_client()

    def setUp(self):
        with m.app.app_context():
            m.Registro.query.delete()
            m.mybd.session.commit()
        open(m.ARQUIVO_REJEITADAS, "w").close()

    def enviar(self, p, **kw):
        m.on_message(None, None, Msg(p, **kw))
        m.fila_gravacao.join()

    def linhas(self):
        with m.app.app_context():
            return m.Registro.query.all()

    def test_mensagem_valida_mapeamento(self):
        self.enviar(payload())
        (r,) = self.linhas()
        self.assertEqual((float(r.temperature), float(r.humidity), float(r.CO2)), (25.5, 60.1, 612.0))
        self.assertEqual((float(r.particula1), float(r.particula2)), (12.3, 8.7))
        self.assertEqual(r.registro_tempo, datetime(2026, 11, 17, 12, 0, 0))
        self.assertFalse(hasattr(r, "pressure"))  # pressure/altitude não são armazenados

    def test_duplicada_ignorada(self):
        self.enviar(payload()); self.enviar(payload())
        self.assertEqual(len(self.linhas()), 1)

    def test_json_invalido(self):
        self.enviar(b"{quebrado")
        self.assertEqual(len(self.linhas()), 0)
        self.assertIn("json inválido", open(m.ARQUIVO_REJEITADAS, encoding="utf-8").read())

    def test_sem_timestamp_ou_nao_numerico(self):
        self.enviar({"temperature": 20})
        self.enviar(payload(t=ts(h=13), temperature="abc"))
        self.enviar(payload(t=ts(h=14), CO2=float("nan")))
        self.enviar(payload(t=0))
        self.assertEqual(len(self.linhas()), 0)

    def test_valor_ausente_vira_null(self):
        p = payload(); del p["CO2"]
        self.enviar(p)
        (r,) = self.linhas()
        self.assertIsNone(r.CO2)

    def test_timestamp_em_ms(self):
        self.enviar(payload(t=ts() * 1000))
        self.assertEqual(self.linhas()[0].registro_tempo, datetime(2026, 11, 17, 12, 0, 0))

    def test_sensor_nao_cadastrado(self):
        with mock.patch.dict(m.TOPICO_PARA_SENSOR, {"outro/topico": "NAO_EXISTE"}):
            self.enviar(payload(), topic="outro/topico")
        self.assertEqual(len(self.linhas()), 0)
        self.assertIn("não cadastrado", open(m.ARQUIVO_REJEITADAS, encoding="utf-8").read())

    def test_banco_cai_e_volta_sem_perder_dado(self):
        original = m.mybd.session.commit
        chamadas = {"n": 0}
        def falha_uma_vez():
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                raise OperationalError("INSERT", {}, Exception("banco fora"))
            return original()
        with mock.patch.object(m, "_parar", m._parar), mock.patch.object(m.mybd.session, "commit", falha_uma_vez):
            m.on_message(None, None, Msg(payload()))
            m.fila_gravacao.join()   # aguarda retry (backoff inicial de 2s)
        self.assertEqual(len(self.linhas()), 1)
        self.assertGreaterEqual(chamadas["n"], 2)

    def test_endpoints(self):
        for h in (10, 11, 12):
            self.enviar(payload(t=ts(h=h), temperature=20 + h))
        r = self.c.get("/health"); self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["banco"], "ok")

        r = self.c.get("/api/leituras"); self.assertEqual(r.json["total"], 3)
        self.assertEqual(r.json["dados"][0]["registro_tempo"], "2026-11-17T12:00:00Z")
        self.assertEqual(set(r.json["dados"][0]), {"id", "sensor", "temperature", "humidity", "CO2",
                                                    "particula1", "particula2", "registro_tempo"})

        r = self.c.get("/api/leituras?inicio=2026-11-17T11:00:00Z&fim=2026-11-17T12:00:00Z&ordem=asc")
        self.assertEqual([d["temperature"] for d in r.json["dados"]], [31.0, 32.0])

        r = self.c.get("/api/leituras/ultima"); self.assertEqual(r.json["temperature"], 32.0)
        self.assertEqual(self.c.get(f"/api/leituras/{r.json['id']}").status_code, 200)
        self.assertEqual(self.c.get("/api/leituras/99999").status_code, 404)

        self.assertEqual(self.c.get("/api/sensores").json[0]["codigo"], "IOT_PADRAO")
        self.assertEqual(self.c.get("/api/sensores/IOT_PADRAO/leituras").json["total"], 3)
        self.assertEqual(self.c.get("/api/sensores/XXX/leituras").status_code, 404)

        r = self.c.get("/api/historico/temperature")
        self.assertEqual([d["valor"] for d in r.json["dados"]], [30.0, 31.0, 32.0])
        self.assertEqual(self.c.get("/api/historico/pressure").status_code, 400)

        self.assertEqual(self.c.get("/api/leituras?inicio=ontem").status_code, 400)
        self.assertEqual(self.c.get("/api/leituras?limit=abc").status_code, 400)
        self.assertEqual(self.c.get("/rota-inexistente").status_code, 404)

        s = self.c.get("/api/mqtt/status").json
        self.assertGreaterEqual(s["recebidas"], 3); self.assertTrue(s["worker_ativo"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
