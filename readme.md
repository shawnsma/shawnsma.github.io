# Personal Website

Static site with a small backend used for the “Brewery Recs” map.

## Tech Stack

- **Backend:** [FastAPI](https://fastapi.tiangolo.com/) (Python)
- **Frontend:** Vanilla HTML + JavaScript with [Leaflet.js](https://leafletjs.com/) for interactive maps

## API

- `GET /` → serves `index.html`
- `GET /api/breweries` → returns a list of breweries used by the map
