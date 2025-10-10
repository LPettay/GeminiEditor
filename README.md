# GeminiEditor v2.0

A sophisticated AI-powered video editing platform with **project-based workflow**, **non-destructive editing**, and an intuitive **text-based editing interface**. Transform long-form video content using OpenAI Whisper for transcription and Google Gemini AI for intelligent segment selection.

## 🎯 What's New in v2.0

**Major Redesign:** Complete architectural overhaul with:
- ✨ **Project Management** - Organize videos and edits in projects
- 🎬 **Text-Based Editing** - Edit video by manipulating transcript segments
- 🔄 **Non-Destructive Editing** - Preview changes without re-encoding
- 💾 **Database-Backed** - All work is saved and versioned
- 🚀 **Deferred Concatenation** - Only export when you're ready

[See the complete redesign documentation →](docs/REDESIGN_PROPOSAL.md)

---

## ✨ Key Features

### 🎯 Project Management
- **Create & organize projects** - Keep all related videos and edits in one place
- **Multiple source videos** per project
- **Version control** - Create multiple edit versions from the same video
- **Edit history** - Never lose your work, iterate freely

### 🎬 Text-Based Editing Interface
- **Visual transcript timeline** - See and edit your video by reading
- **Sequential video player** - Preview edits without exporting
- **Include/exclude segments** - Toggle segments on/off with a click
- **Fine-grained timing** - Trim and extend segments precisely
- **Undo/redo support** - Full edit history with keyboard shortcuts
- **Multi-selection** - Edit multiple segments at once

### 🧠 AI-Powered Processing
- **Whisper transcription** - High-quality speech-to-text with word-level timing
- **Gemini content analysis** - AI selects the best segments based on your prompt
- **Narrative outline generation** - AI identifies key story beats
- **Custom prompts** - Guide the AI with specific instructions

### 🔄 Non-Destructive Workflow
- **EDL-based editing** - All edits stored as decision lists
- **Instant preview** - See changes immediately
- **Deferred export** - Only concatenate when finalizing
- **Multiple versions** - Create variations without re-processing

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.8+**
- **Node.js 18+**
- **FFmpeg** (installed and in PATH)
- **CUDA GPU** (optional, for faster transcription)

### Installation

```bash
# 1. Install backend dependencies
pip install -r requirements.txt

# 2. Initialize database
python -m app.init_db

# 3. Install frontend dependencies
cd frontend
npm install

# 4. (Optional) Migrate existing files
python -m app.migrate_files
```

### Set Up Environment

Create a `.env` file in the project root:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

### Run the Application

```bash
# Terminal 1: Start backend
uvicorn app.main:app --reload

# Terminal 2: Start frontend
cd frontend
npm run dev
```

### Access
- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

---

## 📖 User Guide

### Workflow 1: Create Your First Project

```
1. Open app → Click "New Project"
2. Enter project name and description
3. Project is created → Opens project detail page
```

### Workflow 2: Upload and Process a Video

```
1. In project → "Source Videos" tab
2. Upload video (coming soon: use /analyze endpoint)
3. Video is automatically transcribed
4. Navigate to "Edits" tab
5. Click "Create Edit" → Enter AI prompt
6. AI processes and creates an edit with selected segments
7. Edit opens in text-based editor
```

### Workflow 3: Edit Your Video

```
1. Left side: Sequential video player previews your edit
2. Right side: Transcript timeline with all segments
3. Click segments to:
   - Include/exclude from edit
   - Edit timing (trim/extend)
   - Delete entirely
4. Segments highlight as video plays
5. Click "Save Draft" to save changes
6. Click "Finalize & Export" when ready
7. Download your final video
```

### Workflow 4: Iterate on Edits

```
1. Projects → Select project → "Edits" tab
2. Click existing edit to open in editor
3. Make changes to segments
4. Save draft
5. Or: Duplicate edit to create a new version
6. Finalize when ready
```

---

## 🏗️ Architecture

### Database-Backed Design

```
SQLite Database
├── Projects - Container for all work
│   ├── Source Videos - Uploaded media files
│   │   └── Transcript Segments - Timestamped text
│   └── Edits - Edit versions
│       └── Edit Decisions (EDL) - Clip timeline
```

### Backend (FastAPI + SQLAlchemy)

```
app/
├── main.py                # FastAPI application
├── database.py            # Database configuration
├── models.py              # SQLAlchemy models (5 models)
├── dao.py                 # Data access layer
├── schemas.py             # Pydantic schemas
├── api/                   # API endpoints
│   ├── projects.py        # Projects CRUD
│   ├── source_videos.py   # Video management
│   ├── edits.py           # Edit management
│   └── processing.py      # Processing & export
├── services/
│   └── video_processing.py # AI processing service
├── whisper_utils.py       # Transcription
├── gemini.py              # AI analysis
└── ffmpeg_utils.py        # Video processing
```

### Frontend (React + TypeScript + Zustand)

```
frontend/src/
├── App.tsx                # Routing with React Router
├── api/
│   └── client.ts          # Typed API client
├── store/
│   ├── projectStore.ts    # Project state
│   └── editorStore.ts     # Editor state + undo/redo
├── pages/
│   ├── ProjectListPage.tsx      # Project grid
│   ├── ProjectDetailPage.tsx    # Project tabs
│   └── EditEditorPage.tsx       # Text-based editor
└── components/
    ├── project/           # Project management components
    └── editor/            # Editing interface components
        ├── SequentialVideoPlayer.tsx
        ├── TranscriptTimeline.tsx
        ├── SegmentCard.tsx
        └── TrimExtendModal.tsx
```

---

## 🔌 API Endpoints

### Projects
```
GET    /api/projects                      # List projects
POST   /api/projects                      # Create project
GET    /api/projects/{id}                 # Get project
PATCH  /api/projects/{id}                 # Update project
DELETE /api/projects/{id}                 # Delete project
```

### Source Videos
```
GET    /api/projects/{id}/source-videos              # List videos
GET    /api/projects/{id}/source-videos/{vid}        # Get video
GET    /api/projects/{id}/source-videos/{vid}/transcript # Get transcript
```

### Edits
```
GET    /api/projects/{id}/edits                      # List edits
POST   /api/projects/{id}/edits                      # Create edit
GET    /api/projects/{id}/edits/{eid}                # Get edit
GET    /api/projects/{id}/edits/{eid}/with-decisions # Get edit + EDL
PATCH  /api/projects/{id}/edits/{eid}                # Update edit
POST   /api/projects/{id}/edits/{eid}/duplicate      # Duplicate edit
```

### Edit Decision List (EDL)
```
GET    /api/projects/{id}/edits/{eid}/edl                   # Get EDL
PATCH  /api/projects/{id}/edits/{eid}/edl/{did}             # Update decision
POST   /api/projects/{id}/edits/{eid}/edl/reorder           # Reorder decisions
DELETE /api/projects/{id}/edits/{eid}/edl/{did}             # Delete decision
```

### Processing
```
POST   /api/projects/{id}/source-videos/{vid}/process   # Process video
GET    /api/jobs/{job_id}                               # Get job status
GET    /api/projects/{id}/edits/{eid}/preview           # Get preview data
POST   /api/projects/{id}/edits/{eid}/finalize          # Finalize & export
GET    /api/projects/{id}/edits/{eid}/download          # Download final video
```

[Full API documentation →](http://localhost:8000/docs)

---

## ⚙️ Configuration

### Whisper Models
Choose transcription accuracy vs. speed:
- `tiny` - Fastest, lower accuracy
- `base` - Good balance
- `small` - Better accuracy
- `medium` - **Default** - High accuracy
- `large` - Best accuracy, slowest

### Processing Options
- **Audio Track** - Select which audio stream to use
- **Language** - Transcription language (default: English)
- **Padding** - Seconds to add before/after each segment
- **User Prompt** - Guide AI segment selection

### Editing Settings
- **Allow Reordering** - Let AI reorder segments
- **Allow Repetition** - Allow duplicate segments
- **Vision Extension** - Extend clips based on visual context
- **Simple Mode** - Skip complex AI analysis

---

## 🎬 Advanced Features

### Custom AI Prompts

Guide Gemini's segment selection with specific instructions:

```
"Focus on moments with high energy and audience engagement"
"Select segments that explain key concepts clearly"
"Highlight the most entertaining parts of the stream"
"Create a highlight reel of funny moments"
```

### Scope Trimming

Pre-trim videos before processing:
- Reduces processing time for long videos
- Focus on specific sections
- Set start/end times in seconds

### Multi-Selection & Batch Operations

- Select multiple segments (Shift+click or Select All)
- Toggle inclusion for all selected
- Delete multiple segments at once

### Keyboard Shortcuts (Coming Soon)

- `Ctrl+Z` / `Cmd+Z` - Undo
- `Ctrl+Shift+Z` / `Cmd+Shift+Z` - Redo
- `Ctrl+S` / `Cmd+S` - Save draft
- `Space` - Play/pause
- `←` / `→` - Seek backward/forward

---

## 📁 Data Storage

### Database
- **Location:** `data/gemini_editor.db`
- **Type:** SQLite
- **Backup:** Copy the database file

### Files
- **uploads/** - Original source videos
- **processed/** - Finalized exported videos
- **transcripts/** - Transcript JSON files
- **tmp/** - Temporary processing files

---

## 🛠️ Development

### Database Management

```bash
# Initialize fresh database
python -m app.init_db

# Migrate existing files
python -m app.migrate_files

# Reset database (⚠️ deletes all data)
python -m app.init_db  # Prompts for confirmation
```

### API Development

```bash
# Start with auto-reload
uvicorn app.main:app --reload

# View API docs
open http://localhost:8000/docs

# View alternative docs
open http://localhost:8000/redoc
```

### Frontend Development

```bash
# Development server
cd frontend && npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

---

## 🐛 Troubleshooting

### Common Issues

**Database not found:**
```bash
python -m app.init_db
```

**Frontend not connecting to API:**
- Ensure backend is running on port 8000
- Check CORS configuration in `main.py`

**CUDA not available:**
- Install PyTorch with CUDA support
- Or use CPU-only (slower transcription)

**FFmpeg errors:**
- Ensure FFmpeg is installed and in PATH
- Windows: Download from ffmpeg.org
- Mac: `brew install ffmpeg`
- Linux: `apt-get install ffmpeg`

**Gemini API errors:**
- Verify API key in `.env`
- Check API quota/billing
- Ensure you have Gemini API access

---

## 📚 Documentation

- **[Redesign Proposal](docs/REDESIGN_PROPOSAL.md)** - Complete architecture design
- **[Database Guide](docs/DATABASE.md)** - Database schema and usage
- **[Implementation Progress](docs/IMPLEMENTATION_PROGRESS.md)** - Development timeline
- **[Final Summary](docs/FINAL_SUMMARY.md)** - Complete feature list
- **[API Documentation](http://localhost:8000/docs)** - Interactive API docs

---

## 🎉 What's Working

✅ Complete project management  
✅ Upload and transcribe videos  
✅ AI-powered segment selection  
✅ Text-based editing interface  
✅ Sequential video preview  
✅ Include/exclude segments  
✅ Trim and extend timing  
✅ Save draft edits  
✅ Finalize and export  
✅ Download final videos  
✅ Undo/redo support  
✅ Multi-selection  
✅ Version control  

---

## 🚧 Known Limitations

- Drag-and-drop reordering not yet implemented (use include/exclude)
- Individual clip caching not yet implemented (streaming works)
- Thumbnail generation not yet implemented
- Some keyboard shortcuts not yet wired up

These are **nice-to-have features** that don't block usage.

---

## 🤝 Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

---

## 📄 License

This project is licensed under the MIT License.

---

## 🙏 Acknowledgments

- **OpenAI Whisper** - Speech recognition
- **Google Gemini** - AI content analysis
- **FFmpeg** - Video processing
- **FastAPI** - Backend framework
- **React** - Frontend framework
- **Material-UI** - UI components
- **SQLAlchemy** - Database ORM
- **Zustand** - State management

---

## 📞 Support

For issues, questions, or feature requests:
- Check the [documentation](docs/)
- Review [troubleshooting](#-troubleshooting)
- Open an issue on GitHub

---

**GeminiEditor v2.0** - Transform your videos with AI-powered text-based editing.

*Built with ❤️ using Python, TypeScript, and modern web technologies.*
