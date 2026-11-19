
import os
import json
import time

import paho.mqtt.publish as publish

from dotenv import load_dotenv

load_dotenv()

BROKER = os.getenv("MQTT_BROKER", "test.mosquitto.org")
PORTA = int(os.getenv("MQTT_PORT", 1883))
TOPICO = os.getenv("MQTT_TOPIC")

if not TOPICO:
    raise ValueError("Configure MQTT_TOPIC no arquivo .env")

dados = {
    "temperature": 32.5,
    "pressure": 92954.63,
    "altitude": 776.5,
    "humidity": 78.0,
    "CO2": 1500,
    "particula1": 12.3,
    "particula2": 8.7,
    "timestamp": int(time.time())
}

publish.single(
    topic=TOPICO,
    payload=json.dumps(dados),
    hostname=BROKER,
    port=PORTA,
    qos=1
)

print("Medicao simulada enviada com sucesso!")
print(json.dumps(dados, indent=4))
