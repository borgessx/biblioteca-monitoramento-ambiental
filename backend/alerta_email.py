import os
import base64

from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"   

def autenticar_gmail():
    credenciais = None

    if os.path.exists(TOKEN_FILE):
        credenciais = Credentials.from_authorized_user_file(
            TOKEN_FILE, SCOPES
        )

    if not credenciais or not credenciais.valid:

        if credenciais and credenciais.expired and credenciais.refresh_token:
            credenciais.refresh(Request())

        else:
            fluxo = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )

            credenciais = fluxo.run_local_server(port=0)

        with open(TOKEN_FILE, "w", encoding="utf-8") as arquivo:
            arquivo.write(credenciais.to_json())

    return build("gmail", "v1", credentials=credenciais)    


def enviar_email(destinatario, assunto, mensagem):

    servico = autenticar_gmail()

    email = EmailMessage()

    email["To"] = destinatario
    email["Subject"] = assunto

    email.set_content(mensagem)

    mensagem_codificada = base64.urlsafe_b64encode(
        email.as_bytes()
    ).decode("utf-8")

    resultado = servico.users().messages().send(
        userId="me",
        body={"raw": mensagem_codificada}
    ).execute()

    return resultado

