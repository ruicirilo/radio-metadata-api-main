## Radioplayer metadatas's Now Playing API with Deployment Boilerplate on Digital Ocean 🚀

Easily extract artist and song metadata from MP3 audio streams with this lightweight FastAPI-based application. Simply provide the audio stream URL and receive comprehensive now-playing information, including song title, artist, album art, and song history, in a convenient JSON format.  

The accompanying repository offers a minimalist boilerplate, simplifying the process of deploying your application to Digital Ocean.

## Features

* **Retrieval of now-playing data from an audio stream:** Extracts the complete title information embedded within the audio stream and retrieves the artist, song name, and album art.
* **Stream History Tracking:**  Creates a historical log of played songs, enabling tracking and analysis of listening patterns.
* **Minimal FastAPI Setup:**  Provides a streamlined and efficient FastAPI implementation for easy API development and deployment.
* **Ready-to-deploy on Digital Ocean:**  Includes a basic configuration and boilerplate code for seamless deployment on Digital Ocean servers.
* **Basic configurations for a quick start:** Offers essential settings and parameters to get your application up and running quickly. 

## Requirements

Before running the application, make sure you have the following installed:
- Python 3.x
- FastAPI
- Uvicorn

## Installation

1. Clone the repository: `git clone https://github.com/jailsonsb2/radio-metadata-api`
2. Navigate to the project directory: `cd Radio-Now-Playing-API`
3. Create a virtual environment (recommended): `python -m venv .venv`
4. Activate the virtual environment: 
   - Windows: `.venv\Scripts\activate`
   - macOS/Linux: `source .venv/bin/activate`
5. Install dependencies: `pip install -r requirements.txt`

## Configuration

The application uses a SQLite database (`radio_data.db`) to store stream history. You can customize the database path or other settings by modifying the `main.py` file.


## Quick Start

1. Click the "Deploy to DO" button at the top.
2. Follow the instructions on Digital Ocean to deploy your app.
3. Enjoy your FastAPI app running in the cloud!

[![Deploy to DO](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/jailsonsb2/radio-metadata-api/tree/main)

Don't have an account? Get a $200 bonus to test it out!

[![DigitalOcean Referral Badge](https://web-platforms.sfo2.cdn.digitaloceanspaces.com/WWW/Badge%203.svg)](https://www.digitalocean.com/?refcode=54a7273746ae&utm_campaign=Referral_Invite&utm_medium=Referral_Program&utm_source=badge)

---

## API Endpoints

### Get Stream Title and Album Art
```
GET /get_stream_title/?url={stream_url}
```

**Parameters:**

- `stream_url`:  The URL of the MP3 audio stream.

**Example:**
```
https://twj.es/get_stream_title/?url=https://stream.zeno.fm/yn65fsaurfhvv
```

**Response:**

```json
{
    "title": "Song Title - Artist Name",
    "art": "https://example.com/album-art.jpg" 
}
```


### Get Radio Information and History
```
GET /radio_info/?radio_url={stream_url}
```

**Parameters:**

- `stream_url`:  The URL of the MP3 audio stream.

**Example:**
```
https://twj.es/radio_info/?radio_url=https://stream.zeno.fm/yn65fsaurfhvv
```

**Response:**

```json
{
  "songtitle": "Song Title - Artist Name",
  "artist": "Artist Name",
  "song": "Song Title",
  "art": "https://example.com/album-art.jpg",
  "song_history": [
    {
      "song": {
        "title": "Previous Song Title 1",
        "artist": "Previous Artist 1"
      }
    },
    {
      "song": {
        "title": "Previous Song Title 2",
        "artist": "Previous Artist 2"
      }
    }
    // ... more history entries
  ]
}
```

---

## Troubleshooting

- If you encounter errors, make sure you have installed all the required dependencies and that the audio stream URL is valid. 
- Check the server logs for more detailed error messages.

## Contribution

Contributions are welcome! Feel free to open an issue or submit a pull request for suggestions, bug fixes, or new features.

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/C1C1ZZ2EP)


Happy coding! 🎉

