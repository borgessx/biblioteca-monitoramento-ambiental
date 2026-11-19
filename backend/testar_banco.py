import os
from urllib.parse import quote_plus

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from sqlalchemy import create_engine, text

user   = quote_plus(os.environ.get("DB_USER", "root"))
senha  = quote_plus(os.environ.get("DB_PASSWORD", ""))
host   = os.environ.get("DB_HOST", "127.0.0.1")
porta  = os.environ.get("DB_PORT", "3306")
nome   = os.environ.get("DB_NAME", "monitoramento_bd")

uri = f"mysql+pymysql://{user}:{senha}@{host}:{porta}/{nome}"
print("URI:", uri)

try:
    engine = create_engine(uri)
    with engine.connect() as conn:
        resultado = conn.execute(text("SELECT 1")).fetchone()
        print("Conexão OK:", resultado)
        tabelas = conn.execute(text("SHOW TABLES")).fetchall()
        print("Tabelas encontradas:", [t[0] for t in tabelas])
except Exception as e:
    print("ERRO:", e)
