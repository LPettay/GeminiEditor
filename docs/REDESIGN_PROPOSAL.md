# GeminiEditor Redesign Proposal

## Executive Summary

This document outlines a major architectural redesign of GeminiEditor to transform it from a single-run processing tool into a comprehensive project-based video editing platform with non-destructive, text-based editing capabilities.

## Core Design Principles

1. **Non-Destructive Editing**: Keep original clips intact; only concatenate on final export
2. **Project-Centric Workflow**: All assets, edits, and iterations belong to projects
3. **Text-Driven Editing**: Edit video by manipulating transcript segments visually
4. **Pseudo-Concatenation**: Preview edited sequences without physical file concatenation
5. **State Preservation**: Save edit decisions for iteration and historical tracking

---

## Architecture Overview

### Data Model

#### 1. Project
```typescript
interface Project {
  id: string;                          // UUID
  name: string;                        // User-friendly name
  description?: string;                // Optional project description
  created_at: timestamp;               // Creation timestamp
  updated_at: timestamp;               // Last modified timestamp
  
  // Associated media
  source_videos: SourceVideo[];        // Original uploaded videos
  edits: Edit[];                       // All edit versions for this project
  
  // Project settings
  settings: ProjectSettings;           // Whisper model, audio track preferences, etc.
}

interface ProjectSettings {
  default_whisper_model: string;
  default_audio_track: number;
  transcription_language: string;
  // ... other reusable settings
}
```

#### 2. SourceVideo
```typescript
interface SourceVideo {
  id: string;                          // UUID
  project_id: string;                  // Parent project
  filename: string;                    // Original filename
  file_path: string;                   // Path on disk
  file_size: number;                   // Size in bytes
  duration: number;                    // Duration in seconds
  uploaded_at: timestamp;              // Upload timestamp
  
  // Media info
  video_codec: string;
  audio_tracks: AudioTrack[];          // Available audio tracks
  resolution: { width: number, height: number };
  framerate: number;
  
  // Processing artifacts
  transcript_path?: string;            // Path to full transcript JSON
  transcript_segments: TranscriptSegment[]; // Full transcript
  audio_preview_paths: string[];       // Waveform data files
  
  // Optional scope (pre-trim)
  scope_start?: number;                // If source was trimmed before processing
  scope_end?: number;
}

interface AudioTrack {
  index: number;
  codec: string;
  sample_rate: number;
  channels: number;
  language?: string;
}

interface TranscriptSegment {
  id: string;                          // UUID for this segment
  start: number;                       // Start time in seconds
  end: number;                         // End time in seconds
  text: string;                        // Transcript text
  words?: Word[];                      // Word-level timing (if phrase-level enabled)
  confidence?: number;                 // Transcription confidence
  speaker?: string;                    // Speaker ID (future: diarization)
}

interface Word {
  word: string;
  start: number;
  end: number;
  confidence: number;
}
```

#### 3. Edit (formerly just "output")
```typescript
interface Edit {
  id: string;                          // UUID
  project_id: string;                  // Parent project
  name: string;                        // E.g., "First Draft", "Final Cut"
  version: number;                     // Edit version number
  created_at: timestamp;
  updated_at: timestamp;
  
  // Source references
  source_video_id: string;             // Which source video this edit is based on
  
  // Edit Decision List
  edl: EditDecision[];                 // Ordered list of clips to include
  
  // AI-generated artifacts
  narrative_outline?: string[];        // Gemini-generated outline
  user_prompt?: string;                // Original user prompt
  
  // Processing metadata
  ai_processing_complete: boolean;     // Has Gemini finished?
  multimodal_pass_complete: boolean;   // Has Pass 2 finished?
  
  // Export status
  is_finalized: boolean;               // Has user finalized this edit?
  final_video_path?: string;           // Path to concatenated output (if finalized)
  finalized_at?: timestamp;
  
  // Settings used for this edit
  editing_settings: EditingSettings;
}

interface EditDecision {
  id: string;                          // UUID for this clip decision
  order: number;                       // Position in sequence (0-based)
  
  // Clip definition
  segment_id: string;                  // References TranscriptSegment.id
  source_video_id: string;             // Which source video
  start_time: number;                  // Actual start time (may differ from segment if trimmed)
  end_time: number;                    // Actual end time
  
  // Clip metadata
  transcript_text: string;             // Text for this clip (denormalized for easy display)
  
  // Editing state
  is_included: boolean;                // Is this clip included in the edit?
  is_ai_selected: boolean;             // Was this selected by AI initially?
  user_modified: boolean;              // Has user manually adjusted this?
  
  // Visual/preview artifacts
  clip_file_path?: string;             // Path to individual clip file (if pre-extracted)
  thumbnail_path?: string;             // Path to thumbnail
}

interface EditingSettings {
  pad_before_seconds: number;
  pad_after_seconds: number;
  allow_reordering: boolean;
  allow_repetition: boolean;
  enable_vision_extension: boolean;
  enable_multimodal_pass2: boolean;
  simple_mode: boolean;
  // ... all other editing-related settings
}
```

---

## Key Features & Workflows

### Feature 1: Project Management

#### Create New Project
```
User → "New Project" → Enter name/description → Project created
     → Upload source video(s) → Analysis (transcription + audio extraction)
     → Project now contains source video with transcript
```

#### View Project List
```
User → "Projects" page → Grid/List of projects
     → Show: thumbnail, name, date, # of videos, # of edits
     → Click project → Open project detail view
```

#### Project Detail View
```
Layout:
- Header: Project name, description, settings
- Tabs:
  1. "Source Videos": List of uploaded videos
     - Each video shows: thumbnail, duration, upload date, transcript status
     - Actions: Preview, View Transcript, Delete
  
  2. "Edits": List of edit versions
     - Each edit shows: name, version, status (draft/finalized), date
     - Actions: Open in Editor, Duplicate, Rename, Delete, Download (if finalized)
  
  3. "Settings": Project-level settings
     - Default Whisper model, audio track, language, etc.
```

---

### Feature 2: Pseudo-Concatenation System

#### Backend: Virtual Timeline
Instead of immediately cutting and concatenating:
```python
# Current approach (to be replaced):
cut_and_concatenate(source_video, segments, output_path)

# New approach:
1. Keep EDL in database/JSON: [clip1, clip2, clip3, ...]
2. For preview: Generate a streaming playlist (HLS/DASH) or use range requests
3. For playback: Frontend stitches clips client-side or streams sequentially
4. For export: Run actual concatenation only when user finalizes
```

#### Client-Side Pseudo-Playback
**Option A: Sequential Loading (Simpler)**
```typescript
// Play clips sequentially
currentClip = 0
video.onended = () => {
  currentClip++
  if (currentClip < clips.length) {
    video.src = clips[currentClip].url
    video.play()
  }
}
```

**Option B: HLS/DASH Manifest (More sophisticated)**
```
Generate dynamic M3U8/MPD playlist from EDL
#EXTINF:5.2,
/video/clip1.mp4
#EXTINF:3.8,
/video/clip2.mp4
...
```

**Recommendation**: Start with Option A for MVP, upgrade to Option B for production polish.

#### API Endpoints
```
GET /api/projects/{project_id}/edits/{edit_id}/preview
  → Returns EDL with clip URLs for sequential playback

GET /api/projects/{project_id}/edits/{edit_id}/manifest.m3u8
  → Returns HLS manifest (future enhancement)
```

---

### Feature 3: Text-Based Editing Interface

#### UI Layout
```
┌─────────────────────────────────────────────────────────────┐
│  Project: "My Gaming Stream" > Edit: "First Draft"         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │                                                      │    │
│  │          Video Player (Pseudo-Concatenated)         │    │
│  │                                                      │    │
│  │                    [▶ Play]                         │    │
│  │                                                      │    │
│  │  [────────────●──────────────────] 02:34 / 08:45   │    │
│  │                                                      │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  Timeline & Transcript Editor                               │
│                                                              │
│  Included Segments:                        [Toggle Excluded]│
│  ┌────────────────────────────────────────────────────┐    │
│  │ [1] 00:12-00:28  "Oh my god this is hilarious..." ✓│    │
│  │     ⋮⋮ [drag] [✂️ trim] [➕ extend] [🗑️ remove]     │    │
│  ├────────────────────────────────────────────────────┤    │
│  │ [2] 00:45-01:03  "Wait, what just happened?" ✓     │ ← Current
│  │     ⋮⋮ [drag] [✂️ trim] [➕ extend] [🗑️ remove]     │    │
│  ├────────────────────────────────────────────────────┤    │
│  │ [3] 01:15-01:42  "That's the funniest thing..." ✓  │    │
│  │     ⋮⋮ [drag] [✂️ trim] [➕ extend] [🗑️ remove]     │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  Excluded Segments: (collapsed)                     [Show]  │
│                                                              │
│  Actions: [💾 Save Draft] [🎬 Finalize & Export]           │
└─────────────────────────────────────────────────────────────┘
```

#### Key Interactions

**1. Synchronized Playback**
- As video plays, highlight the current segment in the transcript list
- Scroll to keep current segment visible
- Click any segment → jump to that point in the video

**2. Include/Exclude**
- Checkbox or toggle to include/exclude segments
- Excluded segments move to "Excluded Segments" section (collapsed by default)
- Can re-include by clicking "Show" → selecting from excluded list

**3. Drag & Drop Reordering**
- Grab handle (⋮⋮) to drag segments up/down
- Live reordering of EDL
- Video preview updates immediately

**4. Trim/Extend**
- Click "trim" → open modal with fine-grained time controls
- Adjust start/end times with sliders or numeric input
- Preview the trimmed segment before applying
- "Extend" → expand boundaries to include more context

**5. Merge Adjacent Segments**
- Select two or more consecutive segments
- Click "Merge" → combine into single segment
- Merged segment spans from first start to last end

**6. Split Segment**
- Click "Split" on a segment
- Choose split point (time or word boundary if phrase-level enabled)
- Creates two new segments

**7. Undo/Redo**
- Full undo/redo stack for all edit operations
- Cmd/Ctrl+Z, Cmd/Ctrl+Shift+Z

#### State Management
```typescript
// Redux/Zustand store shape
interface EditorState {
  project: Project;
  currentEdit: Edit;
  edl: EditDecision[];               // Current edit decision list
  
  // Playback state
  isPlaying: boolean;
  currentTime: number;                // Current playback position
  currentClipIndex: number;           // Which clip is playing
  
  // UI state
  selectedSegments: string[];         // IDs of selected segments
  showExcluded: boolean;
  
  // History
  undoStack: EditDecision[][];
  redoStack: EditDecision[][];
  
  // Actions
  toggleSegmentInclusion: (segmentId: string) => void;
  reorderSegment: (fromIndex: number, toIndex: number) => void;
  trimSegment: (segmentId: string, newStart: number, newEnd: number) => void;
  mergeSegments: (segmentIds: string[]) => void;
  splitSegment: (segmentId: string, splitPoint: number) => void;
  saveEdit: () => Promise<void>;
  finalizeEdit: () => Promise<void>;
}
```

---

### Feature 4: Final Export

#### Finalization Workflow
```
1. User reviews edit in text-based editor
2. Clicks "Finalize & Export"
3. Modal appears:
   - Confirm edit decisions
   - Choose output settings (resolution, codec, bitrate)
   - Optional: name this finalized version
4. Backend receives finalization request
5. Backend runs actual cut_and_concatenate on the EDL
6. Progress updates via SSE
7. Final video saved to disk
8. Edit marked as finalized, final_video_path stored
9. User can download finalized video
```

#### API Endpoint
```
POST /api/projects/{project_id}/edits/{edit_id}/finalize
Body: {
  output_settings: {
    resolution: "1920x1080",
    codec: "libx264",
    bitrate: "5M",
    output_name: "Final Cut v1"
  }
}

Response: {
  job_id: "abc123",
  status: "processing"
}

GET /api/jobs/{job_id}/progress  (SSE)
  → Stream progress updates

GET /api/projects/{project_id}/edits/{edit_id}/download
  → Download finalized video
```

---

## Database Schema

### Technology Choice
**Recommendation**: SQLite (for simplicity) or PostgreSQL (for scalability)

### Schema

```sql
-- Projects table
CREATE TABLE projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  settings JSON  -- ProjectSettings as JSON
);

-- Source videos table
CREATE TABLE source_videos (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  file_path TEXT NOT NULL,
  file_size INTEGER,
  duration REAL,
  uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  video_codec TEXT,
  audio_tracks JSON,  -- Array of AudioTrack
  resolution JSON,    -- {width, height}
  framerate REAL,
  transcript_path TEXT,
  audio_preview_paths JSON,  -- Array of paths
  scope_start REAL,
  scope_end REAL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Transcript segments table
CREATE TABLE transcript_segments (
  id TEXT PRIMARY KEY,
  source_video_id TEXT NOT NULL,
  start_time REAL NOT NULL,
  end_time REAL NOT NULL,
  text TEXT NOT NULL,
  words JSON,  -- Array of Word objects
  confidence REAL,
  speaker TEXT,
  FOREIGN KEY (source_video_id) REFERENCES source_videos(id) ON DELETE CASCADE
);

CREATE INDEX idx_transcript_segments_video ON transcript_segments(source_video_id);
CREATE INDEX idx_transcript_segments_time ON transcript_segments(source_video_id, start_time, end_time);

-- Edits table
CREATE TABLE edits (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  name TEXT NOT NULL,
  version INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  source_video_id TEXT NOT NULL,
  narrative_outline JSON,  -- Array of strings
  user_prompt TEXT,
  ai_processing_complete BOOLEAN DEFAULT FALSE,
  multimodal_pass_complete BOOLEAN DEFAULT FALSE,
  is_finalized BOOLEAN DEFAULT FALSE,
  final_video_path TEXT,
  finalized_at TIMESTAMP,
  editing_settings JSON,  -- EditingSettings as JSON
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY (source_video_id) REFERENCES source_videos(id)
);

-- Edit decisions (EDL entries)
CREATE TABLE edit_decisions (
  id TEXT PRIMARY KEY,
  edit_id TEXT NOT NULL,
  order_index INTEGER NOT NULL,
  segment_id TEXT NOT NULL,
  source_video_id TEXT NOT NULL,
  start_time REAL NOT NULL,
  end_time REAL NOT NULL,
  transcript_text TEXT NOT NULL,
  is_included BOOLEAN DEFAULT TRUE,
  is_ai_selected BOOLEAN DEFAULT FALSE,
  user_modified BOOLEAN DEFAULT FALSE,
  clip_file_path TEXT,
  thumbnail_path TEXT,
  FOREIGN KEY (edit_id) REFERENCES edits(id) ON DELETE CASCADE,
  FOREIGN KEY (segment_id) REFERENCES transcript_segments(id),
  FOREIGN KEY (source_video_id) REFERENCES source_videos(id)
);

CREATE INDEX idx_edit_decisions_edit ON edit_decisions(edit_id, order_index);
```

---

## API Endpoints Design

### Projects

```
GET    /api/projects                     # List all projects
POST   /api/projects                     # Create new project
GET    /api/projects/{id}                # Get project details
PATCH  /api/projects/{id}                # Update project
DELETE /api/projects/{id}                # Delete project

GET    /api/projects/{id}/source-videos  # List source videos
GET    /api/projects/{id}/edits          # List edits
```

### Source Videos

```
POST   /api/projects/{project_id}/source-videos/upload   # Upload video
POST   /api/projects/{project_id}/source-videos/analyze  # Trigger analysis
GET    /api/projects/{project_id}/source-videos/{id}     # Get video details
DELETE /api/projects/{project_id}/source-videos/{id}     # Delete video

GET    /api/projects/{project_id}/source-videos/{id}/transcript  # Get transcript
GET    /api/source-videos/{id}/stream                            # Stream video (range requests)
```

### Edits

```
POST   /api/projects/{project_id}/edits                           # Create new edit (from AI or blank)
GET    /api/projects/{project_id}/edits/{id}                      # Get edit details
PATCH  /api/projects/{project_id}/edits/{id}                      # Update edit (save EDL changes)
DELETE /api/projects/{project_id}/edits/{id}                      # Delete edit

GET    /api/projects/{project_id}/edits/{id}/edl                  # Get edit decision list
PATCH  /api/projects/{project_id}/edits/{id}/edl                  # Update EDL

POST   /api/projects/{project_id}/edits/{id}/finalize             # Finalize and export
GET    /api/projects/{project_id}/edits/{id}/download             # Download finalized video
GET    /api/projects/{project_id}/edits/{id}/preview              # Get preview info (clip URLs)
```

### Jobs (for async processing)

```
GET    /api/jobs/{job_id}           # Get job status
GET    /api/jobs/{job_id}/progress  # SSE stream for progress updates
DELETE /api/jobs/{job_id}           # Cancel job
```

---

## Frontend Architecture

### Technology Stack
- **Framework**: React (already in use)
- **State Management**: Zustand or Redux Toolkit
- **UI Library**: Material-UI (already in use)
- **Routing**: React Router
- **Video Player**: Video.js or custom HTML5 video element
- **Drag & Drop**: react-beautiful-dnd or dnd-kit
- **Transcript Sync**: Custom hook with time-based highlighting

### Component Structure

```
src/
├── pages/
│   ├── ProjectListPage.tsx          # List all projects
│   ├── ProjectDetailPage.tsx        # Project overview (tabs)
│   ├── EditEditorPage.tsx           # Text-based editing interface
│   └── VideoAnalysisPage.tsx        # Upload & analysis (existing)
│
├── components/
│   ├── project/
│   │   ├── ProjectCard.tsx          # Project thumbnail card
│   │   ├── ProjectForm.tsx          # Create/edit project form
│   │   └── ProjectSettings.tsx      # Project settings panel
│   │
│   ├── source-video/
│   │   ├── SourceVideoCard.tsx      # Video thumbnail card
│   │   ├── SourceVideoPlayer.tsx    # Video preview player
│   │   └── TranscriptViewer.tsx     # Read-only transcript view
│   │
│   ├── edit/
│   │   ├── EditCard.tsx             # Edit version card
│   │   ├── EditList.tsx             # List of edits
│   │   └── FinalizeModal.tsx        # Finalization dialog
│   │
│   ├── editor/
│   │   ├── VideoPlayer.tsx          # Pseudo-concatenated player
│   │   ├── TranscriptTimeline.tsx   # Main transcript editing UI
│   │   ├── SegmentCard.tsx          # Individual segment card (draggable)
│   │   ├── SegmentTrimModal.tsx     # Trim/extend modal
│   │   ├── ExcludedSegments.tsx     # Collapsed excluded segments
│   │   └── EditorToolbar.tsx        # Save/finalize/undo/redo buttons
│   │
│   └── common/
│       ├── VideoScrubber.tsx        # (existing)
│       ├── WaveformPreview.tsx      # (existing)
│       └── ProgressIndicator.tsx    # SSE progress bar
│
├── hooks/
│   ├── useProject.ts                # Project CRUD operations
│   ├── useEdit.ts                   # Edit CRUD operations
│   ├── useVideoSync.ts              # Video/transcript synchronization
│   ├── useSegmentDragDrop.ts        # Drag & drop logic
│   └── useUndoRedo.ts               # Undo/redo history
│
├── store/
│   ├── projectStore.ts              # Projects state
│   ├── editorStore.ts               # Editor state (EDL, playback)
│   └── uiStore.ts                   # UI state (modals, toasts)
│
└── api/
    ├── projects.ts                  # Project API calls
    ├── sourceVideos.ts              # Source video API calls
    ├── edits.ts                     # Edit API calls
    └── jobs.ts                      # Job/progress API calls
```

### Routing Structure

```
/                                    → ProjectListPage
/projects/new                        → ProjectForm (create)
/projects/:projectId                 → ProjectDetailPage
  - Tab: "Source Videos"
  - Tab: "Edits"
  - Tab: "Settings"

/projects/:projectId/upload          → VideoAnalysisPage (upload new source)

/projects/:projectId/edits/:editId   → EditEditorPage (text-based editor)

/projects/:projectId/edits/:editId/preview  → Full-screen preview mode
```

---

## Migration Strategy

### Phase 1: Database & Backend Restructuring
**Goal**: Implement data model and API without breaking existing functionality

1. **Set up database**
   - Choose SQLite or PostgreSQL
   - Create schema
   - Add ORM (SQLAlchemy recommended)

2. **Create data access layer**
   - Models: Project, SourceVideo, TranscriptSegment, Edit, EditDecision
   - CRUD operations for each model
   - Migration scripts for existing files → database

3. **Refactor existing endpoints**
   - `/analyze` → becomes `/api/projects/{id}/source-videos/upload`
   - `/process` → becomes `/api/projects/{id}/edits` (creates draft edit)
   - Keep old endpoints working temporarily (backwards compatibility)

4. **Implement new API endpoints**
   - Projects CRUD
   - Edits CRUD
   - EDL management

5. **Migrate file storage**
   - Script to scan `uploads/`, `processed/`, `transcripts/`
   - Create projects and source_videos from existing files
   - Populate database with historical data

### Phase 2: Pseudo-Concatenation Backend
**Goal**: Replace immediate concatenation with EDL-based preview system

1. **Refactor video processing flow**
   - After AI selection, save EDL to database instead of cutting video
   - Create individual clip files (optional, for caching)
   - Return edit ID instead of final video path

2. **Implement preview endpoint**
   - `/api/projects/{project_id}/edits/{edit_id}/preview`
   - Returns ordered list of clip URLs/paths
   - Frontend can load clips sequentially

3. **Implement finalization endpoint**
   - `/api/projects/{project_id}/edits/{edit_id}/finalize`
   - Runs cut_and_concatenate on the EDL
   - Uses existing FFmpeg pipeline

4. **Add clip extraction**
   - Extract individual clips from source video based on EDL
   - Cache clips for faster preview loading
   - Clean up old clips periodically

### Phase 3: Frontend - Project Management UI
**Goal**: Allow users to create, view, and manage projects

1. **Project List Page**
   - Grid of project cards
   - Create new project button
   - Search/filter projects

2. **Project Detail Page**
   - Tabs for source videos, edits, settings
   - Upload new source video flow
   - View source video details

3. **Edit List**
   - List edit versions
   - Duplicate, rename, delete edits
   - View edit status (draft/finalized)

4. **Update upload flow**
   - Change from standalone upload to "upload to project"
   - Associate uploaded videos with projects

### Phase 4: Frontend - Text-Based Editor
**Goal**: Build the interactive editing interface

1. **Video Player Component**
   - Load clips sequentially from EDL
   - Handle playback across clip boundaries
   - Emit currentTime events for transcript sync

2. **Transcript Timeline Component**
   - Render EDL as draggable segment cards
   - Highlight current segment during playback
   - Include/exclude toggles

3. **Drag & Drop**
   - Reorder segments
   - Update EDL immediately
   - Optimistic UI updates

4. **Trim/Extend Modals**
   - Fine-grained time controls
   - Preview trimmed segment
   - Save changes to EDL

5. **Undo/Redo**
   - Implement history stack
   - Keyboard shortcuts

6. **Save & Finalize**
   - Save draft button → update EDL in database
   - Finalize button → trigger export job
   - Progress tracking via SSE

### Phase 5: Polish & Optimization

1. **Performance**
   - Lazy load clips
   - Thumbnail generation
   - Waveform caching

2. **UX Improvements**
   - Keyboard shortcuts
   - Smooth scrolling & animations
   - Loading states

3. **Testing**
   - Unit tests for API endpoints
   - Integration tests for workflows
   - E2E tests for critical paths

4. **Documentation**
   - Update README
   - API documentation
   - User guide

---

## Open Questions & Decisions Needed

1. **Clip Pre-Extraction**
   - Should we extract individual clips immediately after AI selection?
   - Or extract on-demand during preview?
   - Trade-off: Storage vs. speed

2. **Video Streaming**
   - Sequential loading (simpler) vs. HLS/DASH manifest (more complex)?
   - For MVP: sequential. For production: HLS.

3. **Undo/Redo Scope**
   - Client-side only (fast, lost on refresh) vs. server-side (persistent)?
   - Recommendation: Client-side with periodic autosave to server

4. **Collaborative Editing**
   - Out of scope for initial redesign
   - Future consideration: real-time editing with WebSockets

5. **Export Formats**
   - Multiple output formats (MP4, WebM, etc.)?
   - Multiple resolutions?
   - Keep it simple initially: single format, single resolution

6. **Mobile Support**
   - Is mobile editing in scope?
   - Recommendation: Focus on desktop first, mobile read-only view

---

## Success Metrics

1. **Functionality**
   - ✅ Users can create and manage multiple projects
   - ✅ Users can preview edits without waiting for concatenation
   - ✅ Users can interactively edit via transcript manipulation
   - ✅ Users can finalize and export edits

2. **Performance**
   - Preview loads in < 2 seconds
   - Edit operations feel instant (< 100ms)
   - Final export completes in reasonable time (similar to current)

3. **Usability**
   - Users understand the project workflow without documentation
   - Text-based editing is intuitive (drag, click, trim)
   - Users can iterate on edits quickly

---

## Timeline Estimate

| Phase | Tasks | Estimated Effort |
|-------|-------|------------------|
| Phase 1: Database & Backend | Schema, models, API, migration | 2-3 weeks |
| Phase 2: Pseudo-Concatenation | EDL preview, clip extraction, finalization | 1-2 weeks |
| Phase 3: Frontend - Projects | Project management UI | 1-2 weeks |
| Phase 4: Frontend - Editor | Text-based editing interface | 2-3 weeks |
| Phase 5: Polish | Performance, UX, testing, docs | 1-2 weeks |
| **Total** | | **7-12 weeks** |

*Note: This assumes full-time development. Adjust proportionally for part-time work.*

---

## Next Steps

1. **Review & Refine This Document**
   - Confirm design decisions
   - Identify missing pieces
   - Prioritize features

2. **Set Up Development Environment**
   - Choose database (SQLite or PostgreSQL)
   - Set up ORM (SQLAlchemy)
   - Create migration scripts

3. **Create Detailed Task List**
   - Break down each phase into individual tasks
   - Assign priorities
   - Track progress

4. **Begin Phase 1 Implementation**
   - Start with database schema
   - Implement models and CRUD operations
   - Test with existing data

---

## Appendix: Example Workflows

### Workflow 1: Creating a New Project and Edit

```
1. User lands on ProjectListPage
2. Clicks "New Project"
3. Enters name: "Gaming Stream Highlights", description
4. Project created → redirected to ProjectDetailPage
5. Clicks "Upload Source Video"
6. Selects video file, uploads
7. Backend analyzes video, extracts audio tracks, generates waveform
8. Returns to ProjectDetailPage, video appears in "Source Videos" tab
9. Clicks "Create Edit" from source video card
10. Modal: "Let AI select clips" or "Start blank"
11. Chooses "Let AI select clips", enters prompt
12. Backend runs Whisper + Gemini, creates draft edit with EDL
13. Progress bar shows processing status
14. When complete, redirected to EditEditorPage
15. Sees video player + transcript timeline with AI-selected segments
16. User reviews, makes adjustments (drag, trim, exclude)
17. Clicks "Save Draft"
18. EDL saved to database
19. Later, clicks "Finalize & Export"
20. Backend concatenates clips, final video saved
21. User downloads finalized video
```

### Workflow 2: Iterating on an Existing Edit

```
1. User opens ProjectDetailPage for existing project
2. Navigates to "Edits" tab
3. Sees list of edit versions: "First Draft", "Revised v2", "Final Cut"
4. Clicks "First Draft" → opens EditEditorPage
5. Reviews edit, decides to make changes
6. Excludes a few segments, reorders others
7. Clicks "Save Draft" → EDL updated
8. Wants to keep this as a new version
9. Clicks "Duplicate Edit" → new edit "First Draft (Copy)" created
10. Makes further changes to the copy
11. Renames to "Revised v3"
12. Finalizes "Revised v3"
13. Downloads final video
```

### Workflow 3: Reviewing an Old Project

```
1. User opens ProjectListPage
2. Searches for "Dark Souls Stream"
3. Clicks project card
4. Sees source videos from months ago
5. Clicks "View Transcript" on a source video
6. Browses transcript to find specific moments
7. Decides to create a new edit with just one segment
8. Clicks "Create Edit" → "Start blank"
9. In EditEditorPage, manually includes desired segments
10. Finalizes and exports new clip
```

---

## Conclusion

This redesign transforms GeminiEditor from a single-use processing tool into a full-fledged video editing platform. The project-centric architecture, non-destructive editing workflow, and text-based interface will dramatically improve usability and enable rapid iteration on video edits.

The phased implementation approach ensures we can build incrementally without breaking existing functionality, and the clear data model provides a solid foundation for future enhancements (collaboration, templates, advanced effects, etc.).

**Ready to proceed?** Let's start by confirming the design decisions and creating a detailed task list.

