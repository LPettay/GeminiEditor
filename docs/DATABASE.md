# Database Setup

## Overview

GeminiEditor uses SQLAlchemy with SQLite to manage projects, source videos, transcripts, edits, and edit decisions.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install SQLAlchemy 2.0.23 and Alembic 1.13.1.

### 2. Initialize Database

Run the initialization script:

```bash
python -m app.init_db
```

This will create a new database at `data/gemini_editor.db` with all necessary tables.

### 3. Start the Application

The database will be automatically initialized on application startup:

```bash
uvicorn app.main:app --reload
```

## Database Schema

### Tables

#### projects
- Core container for all related work
- Contains settings, name, description
- Has many: source_videos, edits

#### source_videos
- Uploaded video files
- Contains media info (codec, resolution, framerate, audio tracks)
- Contains processing artifacts (transcript_path, audio_preview_paths)
- Belongs to: project
- Has many: transcript_segments, edits

#### transcript_segments
- Individual timestamped transcript segments
- Contains: start_time, end_time, text, words (JSON)
- Belongs to: source_video
- Referenced by: edit_decisions

#### edits
- Versions of edited videos
- Contains: name, version, AI processing status, finalization status
- Contains: narrative_outline, user_prompt, editing_settings (JSON)
- Belongs to: project, source_video
- Has many: edit_decisions

#### edit_decisions
- Individual clips in the Edit Decision List (EDL)
- Contains: order_index, start_time, end_time, transcript_text
- Contains: is_included, is_ai_selected, user_modified flags
- Belongs to: edit, segment, source_video

## Database Location

Default: `data/gemini_editor.db`

To change the location, edit `DATABASE_PATH` in `app/database.py`.

## Development

### Reset Database

**⚠️ WARNING: This deletes all data!**

```bash
python -m app.init_db
```

The script will prompt you to confirm before resetting.

### Manual Database Access

Use SQLite CLI or GUI tools:

```bash
sqlite3 data/gemini_editor.db
```

### Enable SQL Logging

For debugging, set `echo=True` in `app/database.py`:

```python
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=True  # Enable SQL logging
)
```

## Data Model Helpers

Models include convenience methods for JSON fields:

```python
# Project settings
project.get_settings()  # Returns dict
project.set_settings({"key": "value"})

# Source video metadata
video.get_audio_tracks()  # Returns list of dicts
video.set_audio_tracks([{...}])

# Transcript segments
segment.get_words()  # Returns list of word timing dicts
segment.set_words([{...}])

# Edit metadata
edit.get_narrative_outline()  # Returns list of strings
edit.set_narrative_outline(["point 1", "point 2"])
```

## Migration Notes

When migrating from the old file-based system:
- Existing files in `uploads/`, `processed/`, `transcripts/` should be imported
- Use the migration script (Phase 1.4) to create database records from existing files
- Old files can be kept for backward compatibility during transition

