# Fan Zone — Client

Frontend application workspace for the Fan Zone personalized sports feed platform.

## Overview
This directory is reserved for the frontend client (React / Next.js / Vite / Mobile application) that consumes the Fan Zone backend APIs.

## API Integration
The backend serves the following primary endpoints at `http://localhost:8000`:
- **Interactive API Docs**: `http://localhost:8000/docs`
- **Main Feed**: `GET /api/v1/feed` (supports `tags`, `publisher`, `date_from`, `date_to`, `tone`, `search`, `page`, `page_size`)
- **Personalized Feed**: `POST /api/v1/feed/personal` (accepts user profile with followed tags, excluded publishers, preferred tones)
- **Single Article**: `GET /api/v1/feed/{article_id}`
- **System Health**: `GET /health` or `GET /api/v1/health`
- **Manual Ingestion Trigger**: `POST /api/v1/ingest/trigger`

## Setup & Development
Once initialized, follow the frontend framework's standard start scripts:
```bash
# Example (once package.json is initialized):
npm install
npm run dev
```
