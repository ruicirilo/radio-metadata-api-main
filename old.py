import asyncio
import urllib.request
from typing import Optional, Tuple, Dict, List
import urllib.parse
import ssl

import requests
import validators
import aiohttp 
from fastapi import FastAPI, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import datetime



app = FastAPI(
    title="Radio Metadata API",
    description="Get real-time metadata from online radio streams!",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = "radio_data"
SONG_HISTORY_LIMIT = 5


# === Configuração do Banco de Dados SQLite ===
DATABASE_URL = "sqlite:///./radio_data.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SongHistory(Base):  # Definição da classe model
    __tablename__ = "song_history"
    id = Column(Integer, primary_key=True, index=True)
    radio_url = Column(String)
    artist = Column(String)
    song = Column(String)
    played_at = Column(DateTime, default=datetime.utcnow)


# Define a classe RadioStation ANTES da função startup_event
class RadioStation(Base):
    __tablename__ = "radio_stations"
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True)  # URL da rádio

Base.metadata.create_all(bind=engine)

# Função para obter uma sessão do banco de dados
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# === Fim da Configuração do Banco de Dados ===

# Função para obter a capa do álbum
def get_album_art(artist: str, song: str) -> Optional[str]:
    try:
        response = requests.get(
            f"https://itunes.apple.com/search?term={artist}+{song}&media=music&limit=1"
        )
        response.raise_for_status()
        data = response.json()
        if data["resultCount"] > 0:
            return data["results"][0]["artworkUrl100"].replace("100x100bb", "512x512bb")
        else:
            return None
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar capa do álbum: {e}")
        return None

# Função assíncrona para obter o título da transmissão de MP3
async def get_mp3_stream_title(streaming_url: str, interval: int = 19200) -> Optional[str]:
    """Obtém o título da transmissão de MP3 a partir dos metadados ICY."""
    needle = b"StreamTitle='"
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.110 Safari/537.36"

    headers = {"Icy-MetaData": "1", "User-Agent": ua}

    async with aiohttp.ClientSession() as session:
        async with session.get(streaming_url, headers=headers) as response:
            meta_data_interval = None
            for key, value in response.headers.items():
                if key.lower() == "icy-metaint":
                    meta_data_interval = int(value)
                    break

            if meta_data_interval is None:
                return None

            offset = 0
            while True:
                await response.content.read(meta_data_interval)  # Descarta dados de áudio
                buffer = await response.content.read(interval)
                title_index = buffer.find(needle)
                if title_index != -1:
                    title = buffer[title_index + len(needle) :].split(b";")[0].decode(
                        "utf-8", errors="replace"
                    )
                    return title
                offset += meta_data_interval + interval

    return None  # Retorna None se o título não for encontrado

# Função para extrair artista e música do título
def extract_artist_and_song(title: str) -> Tuple[str, str]:
    title = title.strip("'")
    if "-" in title:
        artist, song = title.split("-", 1)
        return artist.strip(), song.strip()
    else:
        return "", title.strip()


async def monitor_radio(radio_url: str, background_tasks: BackgroundTasks, db: Session, db_task: Session, name: str = None):
    last_song = {"artist": "", "song": ""}

    while True:
        title = await get_mp3_stream_title(radio_url, 19200)
        if title:
            artist, song = extract_artist_and_song(title)

            # Verifica se a música mudou E se NÃO está no topo do histórico (usando db_task)
            if (artist != last_song["artist"] or song != last_song["song"]) and (
                db_task.query(SongHistory).filter_by(radio_url=radio_url, artist=artist, song=song).order_by(SongHistory.played_at.desc()).first() is None
            ):
                # Salvar no banco de dados apenas se a música mudou e não é repetida
                new_song = SongHistory(radio_url=radio_url, artist=artist, song=song)
                db_task.add(new_song)
                db_task.commit()

                # Atualiza a última música
                last_song = {"artist": artist, "song": song}

        await asyncio.sleep(10) 

# Endpoint raiz - agora redireciona para /docs
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
   return """
   <html>
       <head>
           <meta http-equiv="refresh" content="0; url=/docs" />
       </head>
   </html>
   """

@app.get("/start_monitoring/")
async def start_monitoring(radio_url: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Validação da URL
    if not validators.url(radio_url):
        return JSONResponse({"error": "URL da rádio inválida"}, status_code=400)

    # Verifica se a tarefa com o nome correto está em execução (CORRIGIDO)
    if not any(task.get_name() == f"monitor_{radio_url}" for task in asyncio.all_tasks() if task.done() == False):  
        background_tasks = BackgroundTasks()  # Cria um novo objeto BackgroundTasks
        asyncio.create_task(
            monitor_radio(radio_url, background_tasks, db, db, name=f"monitor_{radio_url}")  # Passa os argumentos corretos (CORRIGIDO)
        )

        # Salva a URL no banco de dados se ela ainda não existir
        existing_station = db.query(RadioStation).filter_by(url=radio_url).first()
        if not existing_station:
            new_station = RadioStation(url=radio_url)
            db.add(new_station)
            db.commit()

        return {"message": f"Monitoramento iniciado para {radio_url}"}
    else:
        return {"message": f"Monitoramento já em andamento para {radio_url}"}


@app.get("/radio_info/")
async def get_radio_info(radio_url: str, db: Session = Depends(get_db)):
    # Consultar o histórico usando a classe SongHistory (CORRIGIDO)
    history = (
        db.query(SongHistory)
        .filter_by(radio_url=radio_url)
        .order_by(SongHistory.played_at.desc())
        .limit(SONG_HISTORY_LIMIT)
        .offset(1)  # Ignorar a primeira música (atual)
        .all()
    )

    # Obter a música atual usando a classe SongHistory (CORRIGIDO)
    current_song = (
        db.query(SongHistory)
        .filter_by(radio_url=radio_url)
        .order_by(SongHistory.played_at.desc())
        .first()
    )

    return {
        "currentSong": current_song.song if current_song else "",
        "currentArtist": current_song.artist if current_song else "",
        "songHistory": [
            {"artist": item.artist, "song": item.song} for item in history
        ],
    }


# Endpoint para obter o histórico de músicas da rádio (do banco de dados)
@app.get("/radio_history/")
async def get_radio_history(
    radio_url: str, limit: int = 10, page: int = 1, db: Session = Depends(get_db)
):
    # Calcula o offset para paginação
    offset = (page - 1) * limit 

    # Usando a classe SongHistory para consultar (CORRIGIDO)
    history = (
        db.query(SongHistory)
        .filter_by(radio_url=radio_url)
        .order_by(SongHistory.played_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [
        {
            "artist": item.artist,
            "song": item.song,
            "played_at": item.played_at.isoformat(),
        }
        for item in history
    ]


@app.get("/get_stream_title/")
async def get_stream_title(
    url: str, interval: Optional[int] = 19200, db: Session = Depends(get_db)
):
    try:
        title = await get_mp3_stream_title(
            url, interval
        )  # Aguarda a função assíncrona
        if title:
            artist, song = extract_artist_and_song(title)
            art_url = get_album_art(
                artist, song
            )  # Aguarda a função assíncrona
            return {"artist": artist, "song": song, "art": art_url}
        else:
            return JSONResponse(
                {"error": "Failed to retrieve stream title"}, status_code=404
            )
    except Exception as e:
        return JSONResponse(
            {"error": f"Error fetching stream: {str(e)}"}, status_code=500
        )


@app.on_event("startup")
async def startup_event():  # <-- Remove o argumento
    """Inicia as tarefas de monitoramento ao iniciar o servidor."""
    db = SessionLocal()
    try:
        radio_stations = db.query(RadioStation).all()
        for station in radio_stations:
            background_tasks = BackgroundTasks()  # <-- Cria um novo objeto aqui!
            asyncio.create_task(
                monitor_radio(station.url, background_tasks, db, db, name=f"monitor_{station.url}") 
            )
    finally:
        db.close()


