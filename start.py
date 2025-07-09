import uvicorn
import os
from pathlib import Path
import logging
from main import app

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

if __name__ == "__main__":
    AUDIO_DIR = os.getenv("AUDIO_DIR", "audio_files")
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 6014))

    # Garantir que diretório de áudio existe
    Path(AUDIO_DIR).mkdir(parents=True, exist_ok=True)

    print(f"""
🚀 Rádio Python FM Iniciando...
🔊 Acesse em: http://{HOST}:{PORT}
📁 Diretório de áudio: {Path(AUDIO_DIR).resolve()}
    """)

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
        timeout_keep_alive=300,
        workers=1
    )
