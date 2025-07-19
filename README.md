# GeminiEditor

A sophisticated AI-powered video editing application that automatically transcribes, analyzes, and intelligently edits video content using OpenAI Whisper and Google Gemini AI. The application features a modern React frontend with real-time progress tracking and a robust FastAPI backend.

## 🎯 Overview

GeminiEditor transforms long-form video content into concise, edited videos by:

1. **Intelligent Transcription**: Using OpenAI Whisper to transcribe audio with precise timestamps
2. **AI-Powered Analysis**: Leveraging Google Gemini to analyze content and select key segments
3. **Smart Video Editing**: Automatically cutting and concatenating selected segments
4. **Real-time Processing**: Providing live progress updates during analysis and processing
5. **Modern Web Interface**: Beautiful React frontend with waveform visualization and video scrubbing

## ✨ Key Features

### 🎬 Video Processing
- **Multi-format Support**: Handles various video formats with FFmpeg
- **Audio Track Selection**: Choose from multiple audio tracks in videos
- **Scope Trimming**: Pre-cut videos to specific time ranges before processing
- **Duplicate Detection**: Prevents re-processing of identical files

### 🧠 AI-Powered Editing
- **Whisper Transcription**: High-quality speech-to-text with word-level timestamps
- **Gemini Content Analysis**: AI-driven segment selection based on user prompts
- **Flexible Editing Strategies**: Chronological or custom reordering of segments
- **Phrase-level Editing**: Advanced editing with word-level precision (optional)

### 🎨 Modern Web Interface
- **Real-time Progress**: Live updates during processing via Server-Sent Events
- **Waveform Visualization**: Interactive audio waveform with scrubbing
- **Video Preview**: Built-in video player with seeking capabilities
- **Dark Theme**: Modern Material-UI interface
- **Responsive Design**: Works on desktop and mobile devices

### ⚙️ Advanced Configuration
- **Silence Detection**: Configurable audio silence thresholds
- **Segment Padding**: Add padding around selected segments
- **Repetition Control**: Allow or prevent segment repetition
- **GPU Acceleration**: CUDA support for faster Whisper processing

## 🏗️ Architecture

### Backend (FastAPI)
```
app/
├── main.py              # FastAPI application with endpoints
├── config.py            # Configuration management
├── whisper_utils.py     # OpenAI Whisper integration
├── gemini.py           # Google Gemini AI integration
├── ffmpeg_utils.py     # Video/audio processing utilities
├── vision.py           # Future clip analysis capabilities
├── utils.py            # Helper functions
└── editing/            # Editing strategy implementations
    ├── base.py         # Base editing strategy
    ├── chronological.py # Chronological editing
    └── custom.py       # Custom reordering editing
```

### Frontend (React + TypeScript)
```
frontend/src/
├── App.tsx             # Main application component
├── components/
│   ├── UploadForm.tsx  # File upload and processing form
│   ├── VideoScrubber.tsx # Video player with scrubbing
│   ├── WaveformPreview.tsx # Audio waveform visualization
│   ├── AudioPreview.tsx # Audio track selection
│   └── DebugPanel.tsx  # Development debugging tools
```

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Node.js 18+
- FFmpeg installed and in PATH
- CUDA-compatible GPU (optional, for faster processing)

### Backend Setup

1. **Clone and navigate to the project**:
   ```bash
   cd GeminiEditor
   ```

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:
   Create a `.env` file in the project root:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

4. **Start the backend server**:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Frontend Setup

1. **Navigate to the frontend directory**:
   ```bash
   cd frontend
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

3. **Start the development server**:
   ```bash
   npm run dev
   ```

4. **Access the application**:
   Open your browser to `http://localhost:5173`

## 📖 Usage

### Basic Workflow

1. **Upload Video**: Drag and drop or select a video file
2. **Analysis**: The system automatically analyzes the video and extracts audio tracks
3. **Configure Settings**: Choose audio track, set scope limits, and configure editing options
4. **Process**: Submit for AI-powered editing with optional custom prompts
5. **Download**: Retrieve the processed video and transcript

### Advanced Features

#### Custom Prompts
Provide specific instructions to Gemini for content selection:
```
"Focus on moments with high energy and audience engagement"
"Select segments that explain key concepts clearly"
"Highlight the most entertaining parts of the stream"
```

#### Scope Trimming
Set start and end times to process only specific portions of long videos.

#### Audio Track Selection
Choose from multiple audio tracks when videos contain multiple audio streams.

#### Editing Strategies
- **Chronological**: Maintain original segment order
- **Custom**: Allow AI to reorder segments for better flow

## 🔧 Configuration

### Environment Variables
- `GEMINI_API_KEY`: Google Gemini API key (required for AI features)

### Processing Options
- **Whisper Model**: Choose from `tiny`, `base`, `small`, `medium`, `large`
- **Silence Threshold**: Adjust audio silence detection sensitivity
- **Segment Padding**: Add padding around selected segments
- **Repetition Control**: Allow or prevent segment repetition

## 🛠️ Development

### Project Structure
```
GeminiEditor/
├── app/                 # Backend FastAPI application
├── frontend/           # React frontend application
├── uploads/            # Uploaded video storage
├── processed/          # Processed video output
├── transcripts/        # Generated transcripts
├── processed_audio/    # Extracted audio files
├── tmp/               # Temporary processing files
└── tools/             # External tools (audiowaveform)
```

### API Endpoints

#### Core Endpoints
- `POST /analyze` - Analyze uploaded video and extract audio tracks
- `POST /process` - Process video with AI editing
- `GET /progress/{job_id}` - Real-time progress updates (SSE)
- `GET /video/{filename}` - Serve video files with range support

#### Utility Endpoints
- `POST /check-duplicate` - Check for duplicate files
- `GET /previews/{filename}` - Serve audio preview files

### Development Commands

```bash
# Backend development
uvicorn app.main:app --reload

# Frontend development
cd frontend && npm run dev

# Build frontend for production
cd frontend && npm run build

# Check CUDA availability
python check_cuda.py
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **OpenAI Whisper** for high-quality speech recognition
- **Google Gemini** for AI-powered content analysis
- **FFmpeg** for video processing capabilities
- **FastAPI** for the robust backend framework
- **React** and **Material-UI** for the modern frontend

## 🐛 Troubleshooting

### Common Issues

1. **CUDA not available**: Install PyTorch with CUDA support or use CPU-only version
2. **FFmpeg not found**: Ensure FFmpeg is installed and in your system PATH
3. **Gemini API errors**: Verify your API key is correct and has sufficient quota
4. **Memory issues**: Use smaller Whisper models for large videos

### Performance Tips

- Use CUDA-enabled PyTorch for faster Whisper processing
- Choose appropriate Whisper model size based on accuracy vs. speed needs
- Enable phrase-level editing only when needed for advanced features
- Use scope trimming for very long videos to reduce processing time 