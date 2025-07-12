from fastapi import FastAPI, Request, Form, UploadFile, File, Response, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os
import time
import asyncio
import logging
import hashlib
import uuid
from collections import deque
from typing import Optional, Set, Dict
from mutagen import File as MutagenFile

app = FastAPI()

AUDIO_DIR = os.getenv("AUDIO_DIR", "audio_files")
Path(AUDIO_DIR).mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("radio")

ADMIN_PASSWORD = "sua senha admim aqui"
SESSIONS: Set[str] = set()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RadioBroadcaster:
    def __init__(self):
        self.playlist: deque = deque()
        self.current_track: Optional[str] = None
        self.current_track_duration: int = 0
        self.playback_start_time: float = 0
        self.is_playing: bool = False
        self.listeners: Set[str] = set()
        self.listeners_queues: Dict[str, asyncio.Queue] = {}
        self.load_playlist()

    def load_playlist(self):
        files = sorted([f for f in os.listdir(AUDIO_DIR) if f.endswith((".mp3", ".wav", ".ogg"))])
        self.playlist = deque(files)
        self.current_track = self.playlist[0] if self.playlist else None

    def advance_track(self):
        if self.playlist:
            self.playlist.rotate(-1)
            self.current_track = self.playlist[0]
            self.playback_start_time = time.time()

    async def broadcast_loop(self):
        self.is_playing = True
        while True:
            if not self.playlist:
                logger.warning("Playlist vazia, aguardando músicas...")
                await asyncio.sleep(5)
                self.load_playlist()
                continue

            track = self.current_track
            path = Path(AUDIO_DIR) / track

            try:
                audio = MutagenFile(path)
                self.current_track_duration = int(audio.info.length) if audio and audio.info else 180
                if hasattr(audio.info, "bitrate") and audio.info.bitrate:
                    bitrate_kbps = audio.info.bitrate // 1000
                    bytes_per_second = audio.info.bitrate // 8
                else:
                    bitrate_kbps = 128
                    bytes_per_second = 128000 // 8
                logger.info(f"Tocando: {track} ({self.current_track_duration}s, {bitrate_kbps}kbps)")
            except Exception as e:
                logger.error(f"Erro lendo duração ou bitrate do arquivo {track}: {e}")
                self.current_track_duration = 180
                bytes_per_second = 128000 // 8

            self.playback_start_time = time.time()

            try:
                with open(path, "rb") as f:
                    chunk_size = 8192
                    bytes_sent = 0
                    start_time = time.time()

                    while chunk := f.read(chunk_size):
                        for client_id, q in list(self.listeners_queues.items()):
                            try:
                                await asyncio.wait_for(q.put(chunk), timeout=0.01)
                            except (asyncio.QueueFull, asyncio.TimeoutError):
                                pass
                        bytes_sent += len(chunk)
                        expected_time = bytes_sent / bytes_per_second
                        elapsed = time.time() - start_time
                        sleep_time = expected_time - elapsed
                        if sleep_time > 0:
                            await asyncio.sleep(sleep_time)
            except Exception as e:
                logger.error(f"Erro na reprodução: {e}")

            self.advance_track()

    def get_current_position(self):
        if self.playback_start_time == 0:
            return 0
        pos = int(time.time() - self.playback_start_time)
        return min(pos, self.current_track_duration)

    def add_listener(self, client_id):
        if client_id not in self.listeners:
            self.listeners.add(client_id)
            self.listeners_queues[client_id] = asyncio.Queue(maxsize=300)
            logger.info(f"Novo ouvinte: {client_id} | Total ouvintes: {len(self.listeners)}")

    def remove_listener(self, client_id):
        self.listeners.discard(client_id)
        self.listeners_queues.pop(client_id, None)
        logger.info(f"Ouvinte saiu: {client_id} | Restantes: {len(self.listeners)}")

broadcaster = RadioBroadcaster()

@app.on_event("startup")
async def startup():
    asyncio.create_task(broadcaster.broadcast_loop())

@app.get("/", response_class=HTMLResponse)
async def homepage():
    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8" />
        <title>🎵 Rádio WebGospel By.Bruno Soares.</title>
        <style>
            body {{
                font-family: sans-serif;
                background: #111827;
                color: #f9fafb;
                text-align: center;
                padding: 2rem;
            }}
            .card {{
                background: #1f2937;
                border-radius: 1rem;
                padding: 2rem;
                max-width: 600px;
                margin: auto;
                box-shadow: 0 10px 20px rgba(0,0,0,0.4);
            }}
            audio {{
                width: 100%;
                margin-top: 1rem;
                border-radius: 0.5rem;
            }}
            .progress {{
                background: #374151;
                height: 10px;
                border-radius: 5px;
                overflow: hidden;
                margin: 1rem 0;
            }}
            .bar {{
                height: 100%;
                background: #3b82f6;
                width: 0%;
                transition: width 0.5s;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>📻 Rádio WebGospel By.Bruno Soares.</h1>
            <p>🎶 Tocando agora: <span id="track">...</span></p>
            <p>👤 Ouvintes: <span id="listeners">0</span></p>
            <div class="progress"><div class="bar" id="bar"></div></div>
            <div><span id="elapsed">0:00</span> / <span id="duration">0:00</span></div>
            <audio controls autoplay id="player">
                <source src="/stream" type="audio/mpeg" />
                Seu navegador não suporta áudio.
            </audio>
        </div>

        <script>
            function formatTime(s) {{
                const m = Math.floor(s / 60);
                const sec = s % 60;
                return `${{m}}:${{sec.toString().padStart(2, '0')}}`;
            }}

            async function update() {{
                const res = await fetch("/status");
                const data = await res.json();
                document.getElementById("track").textContent = data.current_track || "Nenhuma música";
                document.getElementById("listeners").textContent = data.listeners;
                document.getElementById("elapsed").textContent = formatTime(data.current_position);
                document.getElementById("duration").textContent = formatTime(data.duration);

                const percent = data.duration ? Math.min(100, (data.current_position / data.duration) * 100) : 0;
                document.getElementById("bar").style.width = percent + "%";
            }}

            setInterval(update, 1000);
            update();
        </script>
    </body>
    </html>
    """

@app.get("/stream")
async def stream(request: Request):
    client_id = str(uuid.uuid4())  # Identificador único por conexão
    broadcaster.add_listener(client_id)

    async def audio_stream():
        q = broadcaster.listeners_queues[client_id]
        try:
            while True:
                chunk = await q.get()
                yield chunk
        except asyncio.CancelledError:
            pass
        finally:
            broadcaster.remove_listener(client_id)

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")

@app.get("/status")
async def status():
    return {
        "current_track": broadcaster.current_track,
        "current_position": broadcaster.get_current_position(),
        "duration": broadcaster.current_track_duration,
        "listeners": len(broadcaster.listeners)
    }

@app.get("/admin-login", response_class=HTMLResponse)
async def login_page():
    return """
    <form method='post'>
        <h2>Login Administrador</h2>
        Senha: <input type='password' name='password' required>
        <button type='submit'>Entrar</button>
    </form>
    """

@app.post("/admin-login")
async def login_post(password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        token = hashlib.sha256(password.encode()).hexdigest()
        SESSIONS.add(token)
        response = RedirectResponse("/admin", status_code=302)
        response.set_cookie("admin_token", token, httponly=True)
        return response
    return HTMLResponse("Senha incorreta", status_code=401)

def get_admin(request: Request):
    token = request.cookies.get("admin_token")
    if token not in SESSIONS:
        from starlette.exceptions import HTTPException
        raise HTTPException(status_code=307, detail="Redirecionar para login", headers={"Location": "/admin-login"})
    return None

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, auth: None = Depends(get_admin)):
    files = sorted([f for f in os.listdir(AUDIO_DIR) if f.endswith((".mp3", ".wav", ".ogg"))])
    file_list = "".join(
        f"<li>{f} <form method='post' action='/delete/{f}' style='display:inline'><button>Excluir</button></form></li>"
        for f in files
    )
    return f"""
    <html><body>
    <h1>Painel Admin</h1>
    <p>Faixa atual: {broadcaster.current_track or 'Nenhuma música'}</p>
    <p>Ouvintes: {len(broadcaster.listeners)}</p>
    <form action='/upload' method='post' enctype='multipart/form-data'>
        <input type='file' name='file' required><button>Upload</button>
    </form>
    <form action='/next' method='post'><button>Próxima Faixa</button></form>
    <form action='/logout' method='post'><button>Sair</button></form>
    <h3>Playlist:</h3><ul>{file_list}</ul>
    <script>
        setInterval(async () => {{
            const res = await fetch('/status');
            const data = await res.json();
            document.querySelector('p').innerText = `Faixa atual: ${{data.current_track || 'Nenhuma música'}}`;
            document.querySelectorAll('p')[1].innerText = `Ouvintes: ${{data.listeners}}`;
        }}, 2000);
    </script>
    </body></html>
    """

@app.post("/upload")
async def upload(file: UploadFile = File(...), auth: None = Depends(get_admin)):
    filename = Path(file.filename).name
    path = Path(AUDIO_DIR) / filename

    if path.exists() and path.is_dir():
        return HTMLResponse("Erro: nome de diretório inválido", status_code=400)

    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    broadcaster.load_playlist()
    return RedirectResponse("/admin", status_code=303)

@app.post("/next")
async def next_track(auth: None = Depends(get_admin)):
    broadcaster.advance_track()
    return RedirectResponse("/admin", status_code=303)

@app.post("/delete/{filename}")
async def delete_file(filename: str, auth: None = Depends(get_admin)):
    path = Path(AUDIO_DIR) / filename
    if path.exists() and path.is_file():
        path.unlink()
        broadcaster.load_playlist()
    return RedirectResponse("/admin", status_code=303)

@app.post("/logout")
async def logout(request: Request):
    token = request.cookies.get("admin_token")
    if token in SESSIONS:
        SESSIONS.remove(token)
    response = RedirectResponse("/admin-login", status_code=302)
    response.delete_cookie("admin_token")
    return response
