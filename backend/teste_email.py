import os
from dotenv import load_dotenv
from alerta_email import enviar_email

load_dotenv()

destinatario = os.getenv("EMAIL_DESTINATARIO")

if not destinatario:
    raise ValueError("EMAIL_DESTINATARIO não configurado")

assunto = "ALERTA - Monitoramento Ambiental"

mensagem = """
ALERTA AMBIENTAL - BIBLIOTECA SENAI

Foi identificada uma condição ambiental inadequada.

Ambiente: Biblioteca
Sensor: IOT_PADRAO
Indicador: Umidade
Valor registrado: 78%
Limite permitido: 55%

Solicitamos a verificação do ambiente.

Sistema de Monitoramento Ambiental
Projeto Integrador II - Ciencias de Dados
"""

resultado = enviar_email(
    destinatario,
    assunto,
    mensagem
)

print("E-mail enviado com sucesso!")
print("ID da mensagem:", resultado["id"])

