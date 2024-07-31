from typing import Optional, Tuple, Dict
from datetime import datetime, timedelta, timezone

import requests
import aiohttp
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

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
MIN_HISTORY_INTERVAL = 30

# === Configuração do Banco de Dados SQLite ===
DATABASE_URL = "sqlite:///./radio_data.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SongHistory(Base):
    __tablename__ = "song_history"
    id = Column(Integer, primary_key=True, index=True)
    radio_url = Column(String)
    artist = Column(String)
    song = Column(String)
    played_at = Column(DateTime, default=datetime.utcnow)


class RadioStation(Base):
    __tablename__ = "radio_stations"
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True)
    name = Column(String)


class LastPlayedSong(Base):
    """Tabela para armazenar a última música tocada por rádio."""

    __tablename__ = "last_played_song"
    radio_url = Column(String, primary_key=True, index=True)  # URL da rádio como chave primária
    artist = Column(String)
    song = Column(String)
    played_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Base.metadata.create_all(bind=engine)

# Função para obter uma sessão do banco de dados
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# === Fim da Configuração do Banco de Dados ===

# Dicionário para armazenar o timestamp da última música tocada por URL
last_song_timestamp: Dict[str, datetime] = {}


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


async def get_mp3_stream_title(streaming_url: str, interval: int = 19200) -> Optional[str]:
    """Obtém o título da transmissão de MP3 a partir dos metadados ICY."""
    needle = b"StreamTitle='"
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.110 Safari/537.36"
    headers = {"Icy-MetaData": "1", "User-Agent": ua}

    try:
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
                    await response.content.read(meta_data_interval)
                    buffer = await response.content.read(interval)
                    title_index = buffer.find(needle)
                    if title_index != -1:
                        title = buffer[title_index + len(needle) :].split(b";")[0].decode(
                            "utf-8", errors="replace"
                        )
                        return title
                    offset += meta_data_interval + interval
    except (aiohttp.ClientError, ValueError) as e:
        print(f"Erro ao obter título da stream: {e}")
        return None


def extract_artist_and_song(title: str) -> Tuple[str, str]:
    title = title.strip("'")
    if " - " in title:
        artist, song = title.split(" - ", 1)
        return artist.strip(), song.strip()
    else:
        return "", title.strip()


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    return """
   <html>
       <head>
           <meta http-equiv="refresh" content="0; url=/docs" />
       </head>
   </html>
   """


@app.get("/get_stream_title/")
async def get_stream_title(url: str, interval: Optional[int] = 19200, db: Session = Depends(get_db)):
    try:
        title = await get_mp3_stream_title(url, interval)
        if not title:
            raise HTTPException(status_code=404, detail="Failed to retrieve stream title")

        artist, song = extract_artist_and_song(title)
        art_url = get_album_art(artist, song)

        # Obtém a última música tocada do banco de dados
        last_played_db = db.query(LastPlayedSong).filter_by(radio_url=url).first()

        # Verifica se a música mudou e se passou tempo suficiente
        if (
            last_played_db is None
            or (artist, song) != (last_played_db.artist, last_played_db.song)
            and (datetime.now(timezone.utc) - last_played_db.played_at) > timedelta(seconds=MIN_HISTORY_INTERVAL)
        ):
            # Salva a música no histórico
            new_song = SongHistory(radio_url=url, artist=artist, song=song)
            db.add(new_song)

            # Atualiza a última música tocada no banco de dados
            if last_played_db is None:
                last_played_db = LastPlayedSong(radio_url=url, artist=artist, song=song)
                db.add(last_played_db)
            else:
                last_played_db.artist = artist
                last_played_db.song = song
                last_played_db.played_at = datetime.now(timezone.utc)  # Define played_at como aware

            db.commit()

        return {"artist": artist, "song": song, "art": art_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stream: {str(e)}")


@app.get("/radio_info/")
async def get_radio_info(radio_url: str, limit: int = 5, db: Session = Depends(get_db)):
    """Retorna a última música tocada e o histórico da rádio."""

    # Obtém a última música tocada do banco de dados
    last_played = db.query(LastPlayedSong).filter_by(radio_url=radio_url).first()

    # Obtém o histórico da rádio
    history = (
        db.query(SongHistory)
        .filter(SongHistory.radio_url == radio_url)
        .order_by(SongHistory.played_at.desc())
        .limit(limit)
        .all()
    )

    # Formata a resposta JSON
    response = {
        "last_played": {
            "artist": last_played.artist if last_played else None,
            "song": last_played.song if last_played else None,
            "played_at": last_played.played_at.isoformat() if last_played else None,
        },
        "history": [
            {
                "artist": item.artist,
                "song": item.song,
                "played_at": item.played_at.isoformat(),
            }
            for item in history
        ],
    }

    return response

@app.on_event("startup")
async def startup_event():
    """Carrega as últimas músicas tocadas ao iniciar."""
    db = SessionLocal()
    try:
        last_played_records = db.query(LastPlayedSong).all()
        for record in last_played_records:
            # Define o fuso horário para played_at
            record.played_at = record.played_at.replace(tzinfo=timezone.utc) 
    finally:
        db.close()