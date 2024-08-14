from typing import Optional, Tuple, Dict
from datetime import datetime, timedelta, timezone

import requests
import urllib.request

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
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

def fetch_itunes_track_details(artist: str, song: str) -> Optional[Dict]:
    """Busca informações da música na API do iTunes e retorna os detalhes."""
    try:
        search_url = f"https://itunes.apple.com/search?term={artist}+{song}&media=music&limit=1"

        response = requests.get(search_url)
        response.raise_for_status()

        data = response.json()

        if data["resultCount"] > 0:
            track = data["results"][0]

            # Converter a duração de milissegundos para minutos e segundos
            duration_ms = track.get("trackTimeMillis", 0)  # Obtém a duração em ms
            duration_seconds = int(duration_ms) / 1000       # Converte para segundos
            minutes = int(duration_seconds // 60)           # Calcula os minutos
            seconds = int(duration_seconds % 60)            # Calcula os segundos
            duration_formatted = f"{minutes:02}:{seconds:02}" # Formata como "mm:ss"

            return {
                "results": {
                    "artist": track.get("artistName"),
                    "title": track.get("trackName"),
                    "album": track.get("collectionName"),
                    "genre": track.get("primaryGenreName"),
                    "artwork": {
                        "small": track.get("artworkUrl60"),
                        "medium": track.get("artworkUrl100"),
                        "xl": track.get("artworkUrl100").replace("100x100bb", "1000x1000bb") if track.get("artworkUrl100") else None,
                    },
                    "duration": duration_formatted, 
                    "stream": track.get("trackViewUrl"),
                    "explicit": track.get("trackExplicitness"),
                    "year": track.get("releaseDate").split("-")[0] if track.get("releaseDate") else None,
                }
            }
        else:
            return None
    except Exception as e:
        print(f"Erro ao buscar detalhes da faixa na API do iTunes: {e}")
        return None

# Função para obter o título da stream (versão síncrona)
def get_mp3_stream_title(streaming_url: str, interval: int = 19200) -> Optional[str]:
    """Obtém o título da transmissão de MP3 a partir dos metadados ICY."""
    needle = b"StreamTitle='"
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.110 Safari/537.36"
    headers = {"Icy-MetaData": "1", "User-Agent": ua}

    try:
        req = urllib.request.Request(streaming_url, headers=headers)
        response = urllib.request.urlopen(req)

        meta_data_interval = None
        for key, value in response.headers.items():
            if key.lower() == "icy-metaint":
                meta_data_interval = int(value)
                break

        if meta_data_interval is None:
            return None

        offset = 0
        while True:
            response.read(meta_data_interval)
            buffer = response.read(interval)
            title_index = buffer.find(needle)
            if title_index != -1:
                title = buffer[title_index + len(needle):].split(b";")[0].decode(
                    "utf-8", errors="replace"
                )
                return title
            offset += meta_data_interval + interval

    except (urllib.error.URLError, ValueError) as e:
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


@app.get("/title/")
def get_stream_title_endpoint(url: str, interval: Optional[int] = 19200) -> Optional[str]:
    """Obtém o título da transmissão de MP3 a partir dos metadados ICY."""
    return get_mp3_stream_title(url, interval)


@app.get("/get_stream_title/")
def get_stream_title(
    url: str, interval: Optional[int] = 19200, db: Session = Depends(get_db)
):
    try:
        title = get_mp3_stream_title(
            url, interval
        )
        if title:
            artist, song = extract_artist_and_song(title)
            art_url = get_album_art(
                artist, song
            )  
            return {"artist": artist, "song": song, "art": art_url}
        else:
            return JSONResponse(
                {"error": "Failed to retrieve stream title"}, status_code=404
            )
    except Exception as e:
        return JSONResponse(
            {"error": f"Error fetching stream: {str(e)}"}, status_code=500
        )


@app.get("/get_stream_details/")
def get_stream_details(
    url: str, interval: Optional[int] = 19200, db: Session = Depends(get_db)
) -> Dict:
    """
    Obtém os metadados da transmissão de MP3 e busca detalhes da faixa no iTunes.
    """

    try:
        title = get_mp3_stream_title(url, interval)
        if not title:
            raise HTTPException(status_code=404, detail="Failed to retrieve stream title")

        artist, song = extract_artist_and_song(title)

        # Buscar detalhes da faixa no iTunes
        track_details = fetch_itunes_track_details(artist, song)

        if not track_details:
            raise HTTPException(status_code=404, detail="Track details not found")

        # --- (Lógica de atualização do banco de dados - opcional) ---
        # Você pode manter a lógica de atualização do banco de dados aqui se precisar.

        return track_details  # Retorna os detalhes da faixa diretamente

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stream: {str(e)}")


@app.get("/radio_info/")
def get_radio_info(radio_url: str, db: Session = Depends(get_db)):
    """
    Endpoint para informações da rádio, recebendo a URL como parâmetro de consulta.
    """
    try:
        # Obtém o título da stream usando a função get_stream_title
        title = get_mp3_stream_title(radio_url)
        if not title:
            raise HTTPException(status_code=404, detail="Failed to retrieve stream title")

        artist, song = extract_artist_and_song(title)
        # --- art_url = get_album_art(artist, song)

        # --- Lógica de atualização do banco de dados ---
        last_played_db = db.query(LastPlayedSong).filter_by(radio_url=radio_url).first()

        if (
            last_played_db is None
            or (artist, song) != (last_played_db.artist, last_played_db.song)
            and (datetime.utcnow() - last_played_db.played_at) > timedelta(seconds=MIN_HISTORY_INTERVAL)
        ):
            new_song = SongHistory(radio_url=radio_url, artist=artist, song=song)
            db.add(new_song)

            if last_played_db is None:
                last_played_db = LastPlayedSong(radio_url=radio_url, artist=artist, song=song)
                db.add(last_played_db)
            else:
                last_played_db.artist = artist
                last_played_db.song = song
                last_played_db.played_at = datetime.utcnow()

            db.commit()

        # --- Buscar informações para a resposta ---
        last_played = db.query(LastPlayedSong).filter_by(radio_url=radio_url).first()
        history = (
            db.query(SongHistory)
            .filter(SongHistory.radio_url == radio_url)
            .order_by(SongHistory.played_at.desc())
            .limit(SONG_HISTORY_LIMIT)
            .all()
        )
        # --- Fim da busca de informações ---

        # --- Construir a resposta ---
        response = {
            "songtitle": f"{last_played.song if last_played else None} - {last_played.artist if last_played else None}",
            "artist": last_played.artist if last_played else None,
            "song": last_played.song if last_played else None,
            # --- "art": art_url,
            "song_history": [
                {"song": {"title": item.song, "artist": item.artist}} for item in history
            ],
        }
        # --- Fim da construção da resposta ---

        return JSONResponse(content=response)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stream: {str(e)}")

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
