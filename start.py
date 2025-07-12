import uvicorn
import os
from pathlib import Path
import logging
from main import app

# Logging
logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    AUDIO_DIR = os.getenv("AUDIO_DIR", "audio_files")
    Path(AUDIO_DIR).mkdir(parents=True, exist_ok=True)

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 11970))

    print(f"""
    🚀 Rádio Online Iniciada!
    📻 Acesse: http://{HOST}:{PORT}
    🎵 Diretório de áudio: {Path(AUDIO_DIR).resolve()}
    🔐 Painel admin: http://{HOST}:{PORT}/admin-login
    """)

    uvicorn.run(app, host=HOST, port=PORT, timeout_keep_alive=300)
