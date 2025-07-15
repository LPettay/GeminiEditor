from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, UploadFile, Form, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
import os
import shutil
import json
import logging
import sys
import time
from enum import Enum
import torch # Import torch for startup check
import asyncio # Added for running sync Gemini functions in thread pool
from typing import Optional, List, Tuple, Dict, Any
import glob # For finding files
import re # For parsing timestamps from filenames
import subprocess # Added for running ffmpeg and audiowaveform in a thread on Windows
import uuid
from fastapi.staticfiles import StaticFiles

# Changed import for new Gemini functions
from .gemini import (
    generate_narrative_outline, 
    select_segments_for_narrative,
    generate_verbatim_script_pass1,
    VerbatimScriptPass1Input,
    refine_video_with_multimodal_pass2,
    # MultimodalPass2InputSegment # REMOVED as it's no longer used/defined in gemini.py for Pass 2 input
)
from .whisper_utils import transcribe_video, transcribe_audio_with_word_timestamps
from .ffmpeg_utils import cut_and_concatenate, extract_audio_segment
import tempfile # For managing temporary directories for audio segments
# from moviepy.editor import VideoFileClip, concatenate_videoclips # REMOVED MoviePy

# --- Import utilities ---
from .utils import (
    match_quotes_to_timestamps, 
    match_text_segments_to_transcript_timestamps,
    generate_unique_filename,
    save_json_to_file,
    load_json_from_file
)

# --- Import New Config and Editing Strategy ---
from app.config import (
    AppConfig,
    EditingFeatureFlags,
    TranscriptionConfig,
    AudioProcessingConfig,
    GeminiConfig
)
from app.editing import (
    ChronologicalEditingStrategy,
    CustomEditingStrategy
)
# --- End Import New Config and Editing Strategy ---

# Vision stub for future clip analysis
from .vision import GeminiVisionService

# Configure logging to output to both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',  # Include timestamp
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

# Set logging levels for specific modules
logging.getLogger('app.whisper_utils').setLevel(logging.WARNING)  # Reduce whisper_utils logging
logging.getLogger('app.ffmpeg_utils').setLevel(logging.INFO)   # Set ffmpeg_utils logging to INFO

# --- CUDA Check on Startup ---
logger.info("--- Checking CUDA availability on application startup ---")
try:
    cuda_available_on_startup = torch.cuda.is_available()
    if cuda_available_on_startup:
        logger.info("CUDA is AVAILABLE to PyTorch on application startup.")
        logger.info(f"  PyTorch CUDA version: {torch.version.cuda if hasattr(torch.version, 'cuda') else 'N/A'}")
        logger.info(f"  Detected {torch.cuda.device_count()} CUDA capable GPU(s).")
        for i in range(torch.cuda.device_count()):
            logger.info(f"    GPU {i}: {torch.cuda.get_device_name(i)}")
        logger.info(f"  Current CUDA device: {torch.cuda.current_device()} ({torch.cuda.get_device_name(torch.cuda.current_device())})")
    else:
        logger.warning("CUDA is NOT available to PyTorch on application startup. Whisper will use CPU.")
except ImportError:
    logger.error("PyTorch (torch) is not installed. Whisper and CUDA check cannot function.")
except Exception as e:
    logger.error(f"An unexpected error occurred during CUDA check on startup: {e}", exc_info=True)
logger.info("--- CUDA check complete ---")
# --- End CUDA Check ---

# Constants
# GEMINI_CHUNK_SIZE = 250 # Define chunk size for Gemini processing (used for Pass 2) # Now from AppConfig

app = FastAPI()

UPLOAD_DIR = "uploads"
PROCESSED_DIR = "processed"
TRANSCRIPTS_DIR = "transcripts"
PROCESSED_AUDIO_DIR = "processed_audio"

# --- Make directory paths absolute --- 
# Assuming the script main.py is in the 'app' subdirectory of the project root.
# Project root would be one level up from where main.py (__file__) is.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UPLOAD_DIR = os.path.join(_project_root, "uploads")
PROCESSED_DIR = os.path.join(_project_root, "processed")
TRANSCRIPTS_DIR = os.path.join(_project_root, "transcripts")
PROCESSED_AUDIO_DIR = os.path.join(_project_root, "processed_audio")
# --- End making paths absolute ---

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
os.makedirs(PROCESSED_AUDIO_DIR, exist_ok=True)

# Directory for temporary preview clips that the user can listen to when choosing an audio track.
PREVIEW_DIR = os.path.join(_project_root, "tmp", "previews")
os.makedirs(PREVIEW_DIR, exist_ok=True)

# Mount the preview directory so files can be streamed by the browser.
# This will serve both MP3 previews and JSON peaks files
app.mount("/previews", StaticFiles(directory=PREVIEW_DIR), name="previews")

# Temporarily comment out static mount to test routing
# app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Test endpoint to verify routing
@app.get("/test-video")
async def test_video():
    return {"message": "Video endpoint is working"}

@app.get("/test-video-path/{filename:path}")
async def test_video_path(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    return {
        "filename": filename,
        "upload_dir": UPLOAD_DIR,
        "full_path": file_path,
        "exists": os.path.exists(file_path),
        "files_in_upload_dir": os.listdir(UPLOAD_DIR) if os.path.exists(UPLOAD_DIR) else []
    }

# Custom video serving endpoint with range request support
@app.get("/video/{filename:path}")
async def serve_video(filename: str, request: Request):
    """
    Serve video files with proper range request support for seeking.
    """
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    logger.info(f"=== VIDEO REQUEST DEBUG ===")
    logger.info(f"Request URL: {request.url}")
    logger.info(f"Request headers: {dict(request.headers)}")
    logger.info(f"Video request for: {filename}")
    logger.info(f"UPLOAD_DIR: {UPLOAD_DIR}")
    logger.info(f"Looking for file at: {file_path}")
    logger.info(f"File exists: {os.path.exists(file_path)}")
    
    # List files in uploads directory for debugging
    try:
        upload_files = os.listdir(UPLOAD_DIR)
        logger.info(f"Files in uploads directory: {upload_files}")
    except Exception as e:
        logger.error(f"Error listing uploads directory: {e}")
    
    if not os.path.exists(file_path):
        logger.error(f"Video file not found: {file_path}")
        return Response(status_code=404, content="Video not found")
    
    file_size = os.path.getsize(file_path)
    logger.info(f"Video file size: {file_size} bytes")
    
    # Check if this is a range request
    range_header = request.headers.get("range")
    logger.info(f"Range header: {range_header}")
    
    if not range_header:
        # No range request - serve the full file
        logger.info("Serving full video file")
        def file_generator():
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk
        
        return StreamingResponse(
            file_generator(),
            media_type="video/mp4",
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, HEAD",
                "Access-Control-Allow-Headers": "Range"
            }
        )
    
    # Parse range header (e.g., "bytes=0-1023")
    try:
        range_type, range_spec = range_header.split("=")
        if range_type.lower() != "bytes":
            return Response(status_code=400, content="Invalid range type")
        
        start, end = range_spec.split("-")
        start = int(start) if start else 0
        end = int(end) if end else file_size - 1
        
        logger.info(f"Range request: {start}-{end} of {file_size}")
        
        # Validate range
        if start >= file_size or end >= file_size or start > end:
            return Response(status_code=416, content="Range not satisfiable")
        
        content_length = end - start + 1
        
        def range_generator():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk_size = min(8192, remaining)
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
                    remaining -= len(chunk)
        
        logger.info(f"Serving range: {start}-{end} ({content_length} bytes)")
        return StreamingResponse(
            range_generator(),
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(content_length),
                "Accept-Ranges": "bytes",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, HEAD",
                "Access-Control-Allow-Headers": "Range"
            },
            status_code=206
        )
        
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid range header: {range_header}, error: {e}")
        return Response(status_code=400, content="Invalid range header")

# In-memory mapping of file_id → absolute video file path created by /analyze.
file_store: Dict[str, str] = {}

# Path to audiowaveform binary – prefer project-local tools copy
_local_audiowf = os.path.join(_project_root, "tools", "audiowaveform.exe")
AUDIOWAVEFORM_BIN = _local_audiowf if os.path.exists(_local_audiowf) else "audiowaveform"

# Function to generate peaks JSON using audiowaveform
def generate_peaks(mp3_path: str, json_path: str):
    cmd = [
        AUDIOWAVEFORM_BIN,
        "-i", mp3_path,
        "-o", json_path,
        "-z", "256",  # samples per pixel
        "-b", "8",    # 8-bit peaks (tiny)
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except FileNotFoundError:
        logger.error("audiowaveform binary not found (looked for project tools copy or system PATH). Peaks will be missing.")
    except subprocess.CalledProcessError as e:
        logger.warning(f"audiowaveform failed on {mp3_path}: {e}")

# Helper to detect first loud segment (defined before use)
def detect_first_loud(input_file: str, stream_index: int, max_scan_seconds: int = 900) -> float | None:
    """
    Efficiently detect the first loud segment in an audio stream.
    Uses progressive scanning to find audio quickly.
    Filters out brief audio blips to find sustained audio content.
    """
    # Start with a small scan window for quick detection
    initial_scan_seconds = 30  # 30 seconds should be enough for most content
    
    # Progressive scan windows: 30s, 2min, 5min, then max_scan_seconds
    scan_windows = [initial_scan_seconds, 120, 300, max_scan_seconds]
    
    for scan_duration in scan_windows:
        scan_start = time.time()
        logger.debug(f"Scanning first {scan_duration}s for audio...")
        
        # Use a more sensitive approach to detect actual audio start
        # Lower threshold and shorter silence duration to catch early audio
        sd_cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-i", input_file,
            "-map", f"0:{stream_index}",
            # Use a slightly stricter threshold and longer min-silence to avoid
            # treating quiet background hiss as audio.
            "-af", "silencedetect=n=-35dB:d=1.5",
            "-t", str(scan_duration),
            "-f", "null", "-",
        ]
        
        try:
            res = subprocess.run(sd_cmd, capture_output=True, text=True, check=True)
            output = res.stderr
        except subprocess.CalledProcessError as e:
            output = e.stderr  # silencedetect returns non-zero when piped to null

        scan_time = time.time() - scan_start
        logger.debug(f"Scan of {scan_duration}s completed in {scan_time:.2f}s")

        # Parse all silence_start and silence_end events to find sustained audio
        silence_events = []
        for line in output.splitlines():
            if "silence_start:" in line:
                try:
                    ts_part = line.split("silence_start:")[1].split()[0]
                    silence_events.append(("start", float(ts_part)))
                except ValueError:
                    continue
            elif "silence_end:" in line:
                try:
                    ts_part = line.split("silence_end:")[1].split()[0]
                    silence_events.append(("end", float(ts_part)))
                except ValueError:
                    continue
        
        # Sort events by timestamp
        silence_events.sort(key=lambda x: x[1])
        
        # Debug: Log all silence events
        logger.debug(f"Silence events for scan {scan_duration}s: {silence_events}")
        
        # More detailed debug logging
        if silence_events:
            logger.info(f"Track {stream_index}: Found {len(silence_events)} silence events in first {scan_duration}s")
            for i, (event_type, timestamp) in enumerate(silence_events[:5]):  # Log first 5 events
                logger.info(f"Track {stream_index}: Event {i+1}: {event_type} at {timestamp:.3f}s")
        else:
            logger.info(f"Track {stream_index}: No silence events detected in first {scan_duration}s")
        
        # Analyze silence events to find the actual audio start
        if not silence_events:
            # No silence events detected in this window – expand scan window to be certain
            logger.debug(f"No silence events detected in first {scan_duration}s, expanding scan...")
            continue
        
        # Identify candidate audio starts – a silence_end that occurs **well before** the
        # end of the scan window. If it lands right at the window boundary it usually
        # means the scan simply ended while we were still in silence.
        margin = 2.0  # seconds from end of window that we treat as "boundary"
        candidate_start = None
        for ev_type, ts in silence_events:
            if ev_type == "end" and ts < (scan_duration - margin):
                candidate_start = ts
                break  # earliest good candidate

        if candidate_start is not None:
            logger.info(
                f"Found audio start at {candidate_start:.3f}s from silence_end (margin {margin}s)"
            )
            return candidate_start
        
        # If we only have silence_start events but no silence_end events,
        # it means audio started at 0.0s and silence began later
        silence_starts = [timestamp for event_type, timestamp in silence_events if event_type == "start"]
        if silence_starts and not silence_events:
            logger.debug(
                f"Window {scan_duration}s contains only silence so far – expanding scan..."
            )
            continue
        
        # If we found audio start in this scan window, return it
        # Otherwise continue to next scan window
        if silence_events:
            # We already processed this above and should have returned
            # If we get here, it means no clear pattern was found
            logger.debug(f"No clear audio pattern found in first {scan_duration}s, expanding scan...")
            continue
        
        # Fallback: no clear pattern, assume audio starts at 0.0s
        logger.info("No clear audio pattern detected, assuming audio starts at 0.0s")
        return 0.0
    
    # If we scanned the full duration and found nothing, assume silent
    logger.info("No audio detected in any scan window, assuming silent track")
    return None

# --- Progress streaming setup ---
# In-memory queues: job_id -> asyncio.Queue of event dicts {text: str, type?: str, payload?: Any}
progress_queues: Dict[str, "asyncio.Queue[dict]"] = {}

# Utility to emit progress events
async def emit_progress(job_id: str, message: dict):
    queue = progress_queues.get(job_id)
    if queue:
        await queue.put(message)

# Background task that performs audio analysis and sends progress events
async def analyze_worker(job_id: str, input_path: str, preview_duration: int):
    start_time = time.time()
    try:
        await emit_progress(job_id, {"text": "Probing streams"})
        probe_start = time.time()

        probe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_streams", "-print_format", "json",
            input_path,
        ]
        result = await asyncio.to_thread(
            subprocess.run,
            probe_cmd,
            capture_output=True,
            text=True,
        )
        stdout, stderr = result.stdout, result.stderr
        if result.returncode != 0:
            logger.error(f"ffprobe failed: {stderr}")
            await emit_progress(job_id, {"text": "ffprobe failed", "type": "error"})
            return

        probe_time = time.time() - probe_start
        logger.info(f"Stream probing completed in {probe_time:.2f}s")
        await emit_progress(job_id, {"text": f"Stream probing completed in {probe_time:.2f}s"})

        probe_json = json.loads(stdout)

        stream_meta: List[Dict[str, Any]] = []
        for stream in probe_json.get("streams", []):
            stream_meta.append({
                "idx": stream.get("index"),
                "codec": stream.get("codec_name"),
                "channels": stream.get("channels"),
                "duration": float(stream.get("duration", 0)),
                "start_time": float(stream.get("start_time", 0) or 0),
                "lang": stream.get("tags", {}).get("language", "und"),
            })

        logger.info(f"Found {len(stream_meta)} audio tracks")
        await emit_progress(job_id, {"text": f"Found {len(stream_meta)} audio tracks"})

        if not stream_meta:
            await emit_progress(job_id, {"text": "No audio streams found", "type": "done", "payload": {"file_id": job_id, "tracks": []}})
            return

        tracks: List[Dict[str, Any]] = []

        for track_idx, meta in enumerate(stream_meta):
            idx = meta["idx"]
            track_start_time = time.time()
            
            await emit_progress(job_id, {"text": f"Processing track {idx} ({track_idx + 1}/{len(stream_meta)})"})
            
            preview_filename = f"{job_id}_{idx}.mp3"
            preview_path = os.path.join(PREVIEW_DIR, preview_filename)
            in_dur = meta.get("duration", 0)
            duration = preview_duration if preview_duration > 0 else in_dur
            start_ts = 0
            
            # Prefer FFprobe-reported stream start_time if present (>1s)
            start_ts = meta.get("start_time", 0) or 0
            if start_ts < 1.0:
                # Fallback to audio-content analysis
                await emit_progress(job_id, {"text": f"Detecting audio start for track {idx}..."})
                detection_start = time.time()
                first_loud = detect_first_loud(input_path, idx)
                detection_time = time.time() - detection_start
                if first_loud is None:
                    await emit_progress(job_id, {"text": f"Track {idx} is silent – skipping (detection took {detection_time:.2f}s)"})
                    continue
                start_ts = first_loud
            else:
                logger.info(f"Track {idx}: Using FFprobe start_time {start_ts:.3f}s")
                detection_time = 0.0
            
            await emit_progress(job_id, {"text": f"Audio starts at {start_ts:.2f}s (detection took {detection_time:.2f}s)"})
            
            # Debug info for immediate audio tracks
            if start_ts < 1.0:  # If audio starts within first second
                logger.info(f"Track {idx}: Immediate audio detected at {start_ts:.3f}s")
                await emit_progress(job_id, {"text": f"Track {idx}: Immediate audio at {start_ts:.3f}s"})
            else:
                logger.info(f"Track {idx}: Delayed audio detected at {start_ts:.2f}s")
                await emit_progress(job_id, {"text": f"Track {idx}: Delayed audio at {start_ts:.2f}s"})
            
            # Calculate extraction parameters with smart duration adjustment
            # For late audio, extract longer segments to ensure we get enough content
            if start_ts > 60:  # If audio starts after 1 minute
                # Extract longer segment for late audio
                adjusted_duration = min(duration * 3, 60)  # Up to 60 seconds for late audio
            else:
                adjusted_duration = duration
            
            # Add small padding before audio start to capture beginning of speech
            # This helps catch the first few words that might be cut off
            padding_before = 0.5  # 0.5 seconds before detected start
            actual_start = max(0.0, start_ts - padding_before)
            
            # Additional debug info
            logger.info(f"Track {idx}: Final start_ts = {start_ts:.3f}s, actual_start = {actual_start:.3f}s (with {padding_before}s padding)")
            
            await emit_progress(job_id, {"text": f"Extracting {adjusted_duration}s preview from {actual_start:.1f}s..."})
            extraction_start = time.time()
            
            ff_cmd = [
                "ffmpeg", "-nostdin", "-y",
                "-ss", str(actual_start),  # Seek before input for faster seeking
                "-i", input_path,
                "-map", f"0:{idx}",
            ]
            if adjusted_duration > 0:
                ff_cmd += ["-t", str(adjusted_duration)]
            ff_cmd += [
                "-vn",  # No video
                "-acodec", "mp3", 
                "-b:a", "128k",
                "-preset", "ultrafast",  # Fastest encoding preset
                "-threads", "0",  # Use all available CPU threads
                preview_path
            ]

            logger.info(f"Running ffmpeg command: {' '.join(ff_cmd)}")
            
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ff_cmd,
                    capture_output=True,
                    text=True,
                )
                
                extraction_time = time.time() - extraction_start
                
                if result.returncode != 0:
                    logger.error(f"ffmpeg failed with return code {result.returncode}")
                    logger.error(f"ffmpeg stderr: {result.stderr}")
                    logger.error(f"ffmpeg stdout: {result.stdout}")
                    await emit_progress(job_id, {"text": f"FFmpeg failed for track {idx} (extraction took {extraction_time:.2f}s)"})
                else:
                    logger.info(f"ffmpeg completed successfully in {extraction_time:.2f}s")
                    await emit_progress(job_id, {"text": f"Preview extracted in {extraction_time:.2f}s"})
                    
            except Exception as e:
                extraction_time = time.time() - extraction_start
                logger.error(f"Exception running ffmpeg: {e}")
                await emit_progress(job_id, {"text": f"FFmpeg exception for track {idx} (extraction took {extraction_time:.2f}s)"})

            # Verify file was created
            if os.path.exists(preview_path):
                file_size = os.path.getsize(preview_path)
                logger.info(f"Created preview file: {preview_filename} ({file_size} bytes)")
                
                # Generate waveform peaks for the preview
                await emit_progress(job_id, {"text": f"Generating waveform for track {idx}..."})
                peaks_start = time.time()
                
                peaks_filename = f"{job_id}_{idx}_peaks.json"
                peaks_path = os.path.join(PREVIEW_DIR, peaks_filename)
                
                try:
                    await asyncio.to_thread(generate_peaks, preview_path, peaks_path)
                    peaks_time = time.time() - peaks_start
                    logger.info(f"Generated waveform peaks in {peaks_time:.2f}s")
                    await emit_progress(job_id, {"text": f"Waveform generated in {peaks_time:.2f}s"})
                    
                    # Add peaks URL to track entry
                    peaks_url = f"/previews/{peaks_filename}"
                except Exception as e:
                    peaks_time = time.time() - peaks_start
                    logger.warning(f"Failed to generate waveform peaks for track {idx}: {e}")
                    await emit_progress(job_id, {"text": f"Waveform generation failed (took {peaks_time:.2f}s)"})
                    peaks_url = None
                
            else:
                logger.error(f"Failed to create preview file: {preview_path}")
                logger.error(f"ffmpeg command was: {' '.join(ff_cmd)}")
                peaks_url = None

            track_time = time.time() - track_start_time
            logger.info(f"Track {idx} completed in {track_time:.2f}s total (detection: {detection_time:.2f}s, extraction: {extraction_time:.2f}s)")
            await emit_progress(job_id, {"text": f"Track {idx} completed in {track_time:.2f}s"})

            track_entry = {
                **meta,
                "snippet_url": f"/previews/{preview_filename}",
                "peaks_url": peaks_url,
            }
            tracks.append(track_entry)

        total_time = time.time() - start_time
        logger.info(f"All tracks processed in {total_time:.2f}s total")
        await emit_progress(job_id, {"text": f"All tracks processed in {total_time:.2f}s"})
        
        payload = {"file_id": job_id, "tracks": tracks}
        await emit_progress(job_id, {"text": "done", "type": "done", "payload": payload})

    except Exception as e:
        total_time = time.time() - start_time
        logger.exception(f"Analysis worker exception after {total_time:.2f}s")
        try:
            await emit_progress(job_id, {"text": f"Error after {total_time:.2f}s: {e}", "type": "error"})
        except Exception as emit_error:
            logger.error(f"Failed to emit error progress: {emit_error}")
    finally:
        # Cleanup queue after a delay to ensure frontend has time to connect
        await asyncio.sleep(1.0)  # Give frontend more time to connect
        progress_queues.pop(job_id, None)
        logger.info(f"Cleaned up progress queue for job {job_id}")


# SSE endpoint
from fastapi.responses import StreamingResponse


@app.get("/progress/{job_id}")
async def progress_stream(job_id: str):
    queue = progress_queues.get(job_id)
    if queue is None:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    async def event_generator():
        while True:
            msg = await queue.get()
            yield f"data: {json.dumps(msg)}\n\n"
            if msg.get("type") == "done":
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# ------------------------------------------------------------
# Audio-track pre-check – analyse a freshly uploaded video and
# return metadata + short MP3 previews for each audio stream.
# ------------------------------------------------------------


@app.post("/analyze")
async def analyze_video(
    file: UploadFile = File(...),
    preview_duration: int = Form(20, description="Length of each audio preview in seconds. Use 0 or negative to include full track.")
):
    """Inspect an uploaded video, list its audio tracks and expose 20-second previews.

    The client can later call /process with the returned *file_id* and the chosen
    *audio_track* index to skip re-uploading the large video file.
    """

    # Save upload to disk with a unique prefix so multiple concurrent uploads don't clash.
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Record mapping for later reuse by /process
    file_store[file_id] = input_path

    # Create progress queue for this job
    progress_queues[file_id] = asyncio.Queue()

    # Start a background task to perform audio analysis and send progress events
    asyncio.create_task(analyze_worker(file_id, input_path, preview_duration))
    
    # Send initial progress message to ensure queue is working
    asyncio.create_task(emit_progress(file_id, {"text": "Starting analysis...", "type": "progress"}))

    return {"job_id": file_id}

# ------------------------------------------------------------
# Existing /process endpoint below – signature extended to
# accept *file_id* and optional *file* upload.
# ------------------------------------------------------------

@app.post("/process")
async def process_video(
    file: UploadFile | None = File(None),
    file_id: str | None = Form(None, description="Identifier of a previously uploaded video returned by /analyze"),
    prompt: str = Form(""), # User prompt for Gemini
    audio_track: int = Form(0, ge=0, description="The 0-indexed audio track to use from the video."),
    produce_video: bool = Form(True),

    # --- Configurable via AppConfig ---
    # Editing Style and Flags
    # editing_style: EditingStyle = Form(EditingStyle.CHRONOLOGICAL, description="The editing style to apply."), # Removed
    enable_phrase_level_editing: bool = Form(False, description="Enable phrase-level editing (secondary word transcription and future Gemini Pass 3 for phrase scripting)."),
    allow_reordering: bool = Form(False, description="Allow reordering of segments/phrases. This is the primary control for non-chronological video assembly."), # Updated description
    allow_repetition: bool = Form(False, description="Allow repetition of segments/phrases."),
    max_segment_repetitions: int = Form(1, ge=1, description="Max times a segment can be repeated (if segment-level repetition is applicable)."),

    # Transcription settings
    whisper_model: str = Form("medium", description="Name of the Whisper model to use (e.g., tiny, base, small, medium, large)."),
    transcription_language: str = Form("en", description="Language code for transcription (e.g., en, es, fr)."),
    save_speech_audio_file: bool = Form(False, description="Whether to save a separate speech-only audio file."),

    # Audio processing settings for silence detection
    audio_silence_threshold: float = Form(-50.0, le=0.0, description="Silence threshold in dB (e.g., -50.0). Must be <= 0."),
    audio_min_silence_duration: float = Form(0.2, ge=0.0, description="Minimum silence duration in seconds for detection."),
    
    # Gemini settings
    gemini_chunk_processing_size: int = Form(250, ge=1, description="Number of segments per chunk for Gemini Pass 2 processing."),
    reuse_latest_augmented_segments: bool = Form(False, description="Reuse the most recent existing augmented segment file for this video, skipping prior processing including word-level transcription."),
    reuse_latest_pass1_output: bool = Form(False, description="Reuse the most recent Pass 1 verbatim script output for this video, skipping Pass 1 generation."),
    reuse_latest_candidate_video: bool = Form(False, description="Reuse the most recent candidate video and its corresponding Pass 1 script."),

    # Padding around each kept segment (in seconds)
    pad_before_seconds: float = Form(0.5, ge=0.0, description="Seconds to pad *before* each selected segment when extracting video."),
    pad_after_seconds: float = Form(0.5, ge=0.0, description="Seconds to pad *after* each selected segment when extracting video."),

    # New: Optional scope trimming – pre-cut the original video to a shorter range
    scope_start_seconds: float | None = Form(None, description="If provided with scope_end_seconds, trim the input video starting at this second before any processing."),
    scope_end_seconds: float | None = Form(None, description="If provided with scope_start_seconds, trim the input video ending at this second before any processing."),

    # Extra context for Gemini
    video_context: str = Form("", description="Optional short context Gemini should know (e.g. 'Dark Souls 1 livestream, Undead Parish')")
):
    """
    Main endpoint for video processing. Handles:
    1. File upload and management
    2. Video transcription using Whisper
    3. Narrative generation and segment selection/arrangement using Gemini and a selected Editing Strategy
    4. Video editing based on processed segments
    
    Args:
        file: The video file to process
        prompt: User instructions for narrative generation (used by Gemini)
        audio_track: Which audio track to use from the video
        produce_video: Whether to generate the final edited video
        
        # editing_style: The editing style to apply (CHRONOLOGICAL or CUSTOM).
        allow_reordering: If CUSTOM style, allows segments to be reordered.
        allow_repetition: If CUSTOM style, allows segments to be repeated.
        max_segment_repetitions: Max times a segment can be repeated if repetition is allowed.

        whisper_model: Name of the Whisper model for transcription.
        transcription_language: Language code for transcription.
        save_speech_audio: Whether to save speech-only audio.

        audio_silence_threshold: Silence threshold for audio processing.
        audio_min_silence_duration: Minimum silence duration for audio processing.
        
        gemini_chunk_processing_size: Segment chunk size for Gemini Pass 2.
        reuse_latest_augmented_segments: Reuse the most recent existing augmented segment file for this video, skipping prior processing including word-level transcription.
        reuse_latest_pass1_output: Reuse the most recent Pass 1 verbatim script output, skipping Pass 1 generation.
        reuse_latest_candidate_video: Reuse the most recent candidate video and its corresponding Pass 1 script.
    """
    try:
        # --- Construct AppConfig ---
        # print(f"[MAIN DEBUG] Type of editing_style from Form before AppConfig: {type(editing_style)}, value: {editing_style}", flush=True)
        
        app_config = AppConfig(
            # editing_style=editing_style, # Removed
            feature_flags=EditingFeatureFlags(
                enable_phrase_level_editing=enable_phrase_level_editing,
                allow_reordering=allow_reordering,
                allow_repetition=allow_repetition,
                max_segment_repetitions=max_segment_repetitions
            ),
            transcription_config=TranscriptionConfig(
                model_name=whisper_model,
                language=transcription_language,
                save_speech_audio=save_speech_audio_file
            ),
            audio_config=AudioProcessingConfig(
                silence_threshold=audio_silence_threshold,
                min_silence_duration=audio_min_silence_duration
                # audio_enhancement is True by default in AudioProcessingConfig
            ),
            gemini_config=GeminiConfig(
                chunk_size=gemini_chunk_processing_size
                # api_key is loaded from env by default in GeminiConfig
            )
        )
        # print(f"[MAIN DEBUG] Type of app_config.editing_style after AppConfig init: {type(app_config.editing_style)}, value: {app_config.editing_style}", flush=True)

        logger.info(f"Processing video with AppConfig: {app_config.model_dump_json(indent=2)}")
        # --- End Construct AppConfig ---

        logger.info(f"Starting processing for file: {file.filename}")
        run_timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        # Resolve the video source – either freshly uploaded or referenced by *file_id*
        if file is not None:
            input_path = os.path.join(UPLOAD_DIR, file.filename)
            if not os.path.exists(input_path):
                logger.info(f"Saving uploaded file to: {input_path}")
                with open(input_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                logger.info("File saved successfully")
            else:
                logger.info(f"Using existing file on disk: {input_path}")

            # Register a mapping so the UI can reference this video later if needed
            generated_file_id = str(uuid.uuid4())
            file_store[generated_file_id] = input_path
            logger.info(f"Assigned file_id {generated_file_id} to uploaded file")

        elif file_id is not None:
            if file_id not in file_store:
                return JSONResponse(status_code=400, content={"message": f"Unknown file_id '{file_id}'"})
            input_path = file_store[file_id]
            logger.info(f"Using previously uploaded file via file_id {file_id}: {input_path}")
        else:
            return JSONResponse(status_code=400, content={"message": "Either 'file' or 'file_id' must be provided."})

        base_name = os.path.splitext(os.path.basename(input_path))[0]

        # --- OPTIONAL SCOPE PRE-TRIM -------------------------------------
        if scope_start_seconds is not None and scope_end_seconds is not None:
            if scope_end_seconds <= scope_start_seconds:
                raise ValueError("scope_end_seconds must be greater than scope_start_seconds")

            trimmed_name = f"{base_name}_scope_{int(scope_start_seconds)}-{int(scope_end_seconds)}.mp4"
            trimmed_path = os.path.join(UPLOAD_DIR, trimmed_name)

            if not os.path.exists(trimmed_path):
                logger.info(f"Trimming input video to scope {scope_start_seconds:.2f}s – {scope_end_seconds:.2f}s → {trimmed_path}")
                ff_cmd = [
                    "ffmpeg", "-nostdin", "-y",
                    "-ss", str(scope_start_seconds),
                    "-to", str(scope_end_seconds),
                    "-i", input_path,
                    "-c", "copy",
                    trimmed_path,
                ]
                subprocess.run(ff_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            else:
                logger.info(f"Using existing trimmed scope file: {trimmed_path}")

            # Use trimmed file for the rest of the pipeline
            input_path = trimmed_path
            base_name = os.path.splitext(os.path.basename(trimmed_path))[0]
            logger.info(f"Scope trimming complete. New input path: {input_path}")
        elif (scope_start_seconds is None) ^ (scope_end_seconds is None):
            logger.warning("Only one of scope_start_seconds / scope_end_seconds provided; ignoring scope trim.")
        # --- END SCOPE PRE-TRIM -----------------------------------------

        # Set up predictable paths for transcript and speech audio
        predictable_transcript_path = os.path.join(TRANSCRIPTS_DIR, f"{base_name}_full_transcription.json")
        predictable_speech_audio_path = None
        if app_config.transcription_config.save_speech_audio: # Use AppConfig
            predictable_speech_audio_path = os.path.join(PROCESSED_AUDIO_DIR, f"{base_name}_speech_only.wav")

        transcript_data = None
        transcript_source_message = ""

        # 1. Transcription (or load existing)
        if os.path.exists(predictable_transcript_path):
            logger.info(f"Reusing existing transcript from: {predictable_transcript_path}")
            try:
                with open(predictable_transcript_path, "r", encoding="utf-8") as f:
                    transcript_data = json.load(f)
                transcript_source_message = f"Reused transcript from {predictable_transcript_path}"
                if app_config.transcription_config.save_speech_audio and predictable_speech_audio_path and not os.path.exists(predictable_speech_audio_path): # Use AppConfig
                    logger.warning(f"Transcript reused, but speech-only audio {predictable_speech_audio_path} not found. It was not generated with the reused transcript.")
                elif app_config.transcription_config.save_speech_audio and predictable_speech_audio_path and os.path.exists(predictable_speech_audio_path): # Use AppConfig
                    logger.info(f"Reusing existing speech-only audio: {predictable_speech_audio_path}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode existing transcript {predictable_transcript_path}: {e}. Will attempt re-transcription.")
                transcript_data = None
            except Exception as e:
                logger.error(f"Unexpected error loading existing transcript {predictable_transcript_path}: {e}. Will attempt re-transcription.", exc_info=True)
                transcript_data = None
        
        if transcript_data is None:
            logger.info(f"No reusable transcript found or loading failed. Starting fresh transcription for {file.filename}...")
            if app_config.transcription_config.save_speech_audio and predictable_speech_audio_path: # Use AppConfig
                 logger.info(f"Speech-only audio will be saved to: {predictable_speech_audio_path}")
            try:
                transcript_data = await asyncio.to_thread( # Assuming transcribe_video is sync
                    transcribe_video,
                    input_path,
                    model_name=app_config.transcription_config.model_name, # Use AppConfig
                    language=app_config.transcription_config.language, # Use AppConfig
                    audio_track=audio_track,
                    silence_duration=app_config.audio_config.min_silence_duration, # Use AppConfig
                    silence_threshold=app_config.audio_config.silence_threshold, # Use AppConfig
                    save_speech_audio_path=predictable_speech_audio_path # Remains conditional
                )
                logger.info(f"Transcription complete. Got {len(transcript_data['segments'])} segments.")
                transcript_source_message = f"Newly generated transcript for {file.filename}"
                with open(predictable_transcript_path, "w", encoding="utf-8") as f:
                    json.dump(transcript_data, f, ensure_ascii=False, indent=2)
                logger.info(f"New transcript saved for reuse to: {predictable_transcript_path}")
                if predictable_speech_audio_path and os.path.exists(predictable_speech_audio_path):
                    logger.info(f"Speech-only audio saved to: {predictable_speech_audio_path}")
            except Exception as e:
                logger.error(f"Transcription failed: {str(e)}", exc_info=True)
                raise

        if not transcript_data or 'segments' not in transcript_data:
            logger.error("Critical error: Transcript data is missing or invalid after attempt to load/generate.")
            return JSONResponse(status_code=500, content={"message": "Failed to obtain transcript data."})

        gemini_processed_segments_path = None
        
        # Prepare a list of segment dicts {'start', 'end', 'text'} for Gemini processing
        all_transcript_segments_structured = [
            {
                "start": seg.get("start"), 
                "end": seg.get("end"), 
                "text": seg.get("text", "")
            }
            for seg in transcript_data['segments']
            if seg.get("start") is not None and seg.get("end") is not None
        ]

        # Default to using all transcribed segments if Gemini processing is skipped or fails entirely
        segments_from_gemini_or_full_transcript = all_transcript_segments_structured

        user_provided_prompt_for_gemini = prompt.strip()
        if not user_provided_prompt_for_gemini:
            gemini_user_prompt_to_use = "Create a highly entertaining video edited in the style of popular online comedians like Jerma985, BedBanana, or General Sam. Focus on highlighting the speaker\'s unique personality, comedic timing, absurd moments, and genuine reactions. Prioritize fast-paced, funny, and engaging mini-narratives or highlight reel moments. If there are setups and punchlines for jokes, try to capture them."
            logger.info("No specific user prompt provided. Using new default instructions for Gemini to create a funny/engaging video.")
        else:
            gemini_user_prompt_to_use = user_provided_prompt_for_gemini
            logger.info(f"Using user-provided prompt for Gemini: '{gemini_user_prompt_to_use[:70]}...'")

        # Helper function to find the most recent file matching a pattern
        def find_most_recent_file(directory: str, base_filename: str, prefix: str, suffix: str = ".json") -> Optional[str]:
            """Finds the most recent file in a directory matching a pattern with an embedded timestamp."""
            # Pattern: prefix_YYYYMMDD_HHMMSS_suffix, e.g., basename_augmented_segments_20231027_153000.json
            # We need to construct the glob pattern carefully to capture the timestamp part for sorting.
            # The timestamp format is YYYYMMDD_HHMMSS
            glob_pattern = os.path.join(directory, f"{base_filename}_{prefix}_*_*{suffix}")
            matching_files = glob.glob(glob_pattern)
            
            if not matching_files:
                return None

            # Extract timestamps and sort
            # Example filename: somevideo_augmented_segments_20231027_153000.json
            # Regex to capture the timestamp part: (YYYYMMDD_HHMMSS)
            # The pattern is base_prefix_timestamp.json
            # So, we expect something like {base_filename}_{prefix}_{timestamp_str}{suffix}
            # Let's try to be more robust: find last underscore before suffix, then go back from there.
            # For f"{base_filename}_{prefix}_*_*{suffix}" it should be `_(\d{8})_(\d{6})\.`
            # Simpler if we know the exact prefix: f"{base_filename}_{prefix}_(\\d{8}_\\d{6}){suffix}"

            file_timestamps = []
            # Regex to extract YYYYMMDD_HHMMSS from filenames like "basename_prefix_YYYYMMDD_HHMMSS.json"
            # It assumes the timestamp is directly after "{base_filename}_{prefix}_"
            pattern_str = f"^{re.escape(base_filename)}_{re.escape(prefix)}_(\\d{{8}}_\\d{{6}}){re.escape(suffix)}$"
            # logger.debug(f"Using regex pattern: {pattern_str} on directory: {directory}")
            
            for f_path in matching_files:
                f_name = os.path.basename(f_path)
                # logger.debug(f"Checking filename: {f_name}")
                match = re.match(pattern_str, f_name)
                if match:
                    timestamp_str = match.group(1) # YYYYMMDD_HHMMSS
                    try:
                        # Convert to time object for sorting, though string sort YYYYMMDD_HHMMSS also works
                        dt_object = time.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                        file_timestamps.append((dt_object, f_path))
                    except ValueError:
                        logger.warning(f"Could not parse timestamp from filename: {f_name}")
                # else:
                    # logger.debug(f"Filename {f_name} did not match expected pattern.")

            if not file_timestamps:
                logger.info(f"No files with parseable timestamps found for pattern {glob_pattern}")
                return None

            file_timestamps.sort(key=lambda x: x[0], reverse=True) # Sort by datetime object, descending
            return file_timestamps[0][1] # Return path of the most recent file

        # ---- Start: Potentially skip Gemini Pass 1 & 2 and word-level by reusing output ----
        gemini_output_reused = False
        reused_data_is_already_augmented = False

        # Logic for reusing latest augmented segments file
        if app_config.feature_flags.enable_phrase_level_editing and reuse_latest_augmented_segments:
            logger.info(f"Attempting to reuse latest augmented segments file for base: {base_name} (flag is True).")
            # File pattern: basename_augmented_segments_{timestamp}.json
            latest_augmented_file = find_most_recent_file(TRANSCRIPTS_DIR, base_name, "augmented_segments")
            
            if latest_augmented_file:
                logger.info(f"Found most recent augmented segment file: {latest_augmented_file}")
                try:
                    with open(latest_augmented_file, "r", encoding="utf-8") as f_reused:
                        reused_segments_data = json.load(f_reused)
                    if isinstance(reused_segments_data, list) and reused_segments_data:
                        segments_from_gemini_or_full_transcript = reused_segments_data
                        gemini_output_reused = True
                        reused_data_is_already_augmented = True # By definition, as we looked for an augmented file
                        gemini_processed_segments_path = latest_augmented_file 
                        logger.info(f"Successfully loaded {len(segments_from_gemini_or_full_transcript)} segments from reused augmented file. Gemini Pass 1, 2 and word-level transcription will be skipped.")
                    else:
                        logger.warning(f"Reused file {latest_augmented_file} did not contain a valid list of segments. Proceeding with full processing.")
                except json.JSONDecodeError as json_e:
                    logger.error(f"Failed to decode JSON from reused file {latest_augmented_file}: {json_e}. Proceeding with full processing.")
                except Exception as e_reused_load:
                    logger.error(f"Unexpected error loading reused file {latest_augmented_file}: {e_reused_load}. Proceeding with full processing.", exc_info=True)
            else:
                logger.info(f"No existing augmented segment file found to reuse for base: {base_name}. Proceeding with full processing.")
        elif reuse_latest_augmented_segments: # Flag is true but phrase editing might be off
            logger.info("'reuse_latest_augmented_segments' is True, but phrase-level editing is not enabled. This flag only applies if phrase-level editing is active. Proceeding with normal flow.")

        # ---- End: Potentially skip processing stages ----

        if not all_transcript_segments_structured and not gemini_output_reused:
            logger.warning("No valid segments from transcription to send to Gemini, and no reused data. Skipping Gemini processing.")
        elif not gemini_output_reused: # Only run Gemini Pass 1 & 2 if not reusing output
            # --- Intermediate Step 1: Generate Verbatim Script with Pass 1 ---
            logger.info("--- Starting Intermediate Step 1: Generate Verbatim Script (Pass 1) ---")
            pass1_verbatim_script_content: Optional[str] = None
            pass1_verbatim_script_path = os.path.join(TRANSCRIPTS_DIR, f"{base_name}_pass1_verbatim_script_{run_timestamp}.txt") # Default save path for new/reused P1
            parsed_pass1_quotes: List[str] = [] # Initialize here

            if reuse_latest_pass1_output:
                logger.info(f"Attempting to reuse latest Pass 1 output (initial check) for base name: {base_name}")
                # Find the most recent pass1_verbatim_script for this base_name
                glob_pattern = os.path.join(TRANSCRIPTS_DIR, f"{base_name}_pass1_verbatim_script_*.txt")
                
                # --- BEGIN DIAGNOSTIC LOG --- 
                try:
                    logger.info(f"[DIAGNOSTIC] Listing contents of TRANSCRIPTS_DIR ('{TRANSCRIPTS_DIR}'): {os.listdir(TRANSCRIPTS_DIR)}")
                except Exception as e_diag_list:
                    logger.error(f"[DIAGNOSTIC] Error listing TRANSCRIPTS_DIR: {e_diag_list}")
                logger.info(f"[DIAGNOSTIC] Using glob pattern: {glob_pattern}")
                # --- END DIAGNOSTIC LOG ---
                
                candidate_files = glob.glob(glob_pattern)
                # --- BEGIN DIAGNOSTIC LOG for glob result ---
                logger.info(f"[DIAGNOSTIC] glob.glob('{glob_pattern}') returned: {candidate_files}")
                # --- END DIAGNOSTIC LOG for glob result ---
                latest_file_path = None
                latest_timestamp_str = ""

                if candidate_files:
                    for f_path in candidate_files:
                        f_name = os.path.basename(f_path)
                        # Regex to extract timestamp: looks for base_name_pass1_verbatim_script_(YYYYMMDD_HHMMSS).txt
                        regex_pattern = rf"{re.escape(base_name)}_pass1_verbatim_script_(\d{{8}}_\d{{6}})\.txt"
                        match = re.search(regex_pattern, f_name)
                        
                        # --- BEGIN DIAGNOSTIC LOG for regex match attempt ---
                        logger.info(f"[DIAGNOSTIC] Checking f_name: '{f_name}' against regex: '{regex_pattern}'. Match found: {match is not None}")
                        if match:
                            logger.info(f"[DIAGNOSTIC] Regex matched. Group 1 (timestamp_str): '{match.group(1)}'")
                        # --- END DIAGNOSTIC LOG for regex match attempt ---
                        
                        if match:
                            timestamp_str = match.group(1)
                            if timestamp_str > latest_timestamp_str: # String comparison works for YYYYMMDD_HHMMSS
                                latest_timestamp_str = timestamp_str
                                latest_file_path = f_path
                
                    if latest_file_path:
                        logger.info(f"Found most recent Pass 1 output to reuse (initial check): {latest_file_path}")
                        try:
                            with open(latest_file_path, "r", encoding="utf-8") as f:
                                pass1_verbatim_script_content = f.read()
                            pass1_verbatim_script_path = latest_file_path # Update path to the reused file
                            logger.info(f"Successfully loaded content from reused Pass 1 file (initial check). Length: {len(pass1_verbatim_script_content)} chars.")
                        except Exception as e_read_reuse:
                            logger.warning(f"Failed to read reused Pass 1 file (initial check) '{latest_file_path}': {e_read_reuse}. Will generate a new Pass 1 script.", exc_info=True)
                            pass1_verbatim_script_content = None 
                    else:
                        logger.info(f"No previous Pass 1 output files found matching pattern (initial check) for base name '{base_name}'. Will generate a new Pass 1 script.")
                else:
                    logger.info(f"No Pass 1 output files found with glob pattern (initial check) '{glob_pattern}'. Will generate a new Pass 1 script.")

            if pass1_verbatim_script_content is None: # If not reused or initial reuse failed
                logger.info("Generating new Pass 1 verbatim script as initial reuse was not enabled or no suitable file was found.")
                
                # --- Define full_transcript_text_for_p1 --- 
                # Build transcript text as one segment per line so that long pauses remain separate.
                if "segments" in transcript_data and isinstance(transcript_data["segments"], list):
                    full_transcript_text_for_p1 = "\n".join(seg.get("text", "") for seg in transcript_data["segments"])
                else:
                    full_transcript_text_for_p1 = transcript_data.get("text", "")

                if not full_transcript_text_for_p1:
                    logger.error("Full transcript text is empty or missing from transcript_data. Cannot proceed with Pass 1.")
                    # This is a critical issue, return an error response
                    return JSONResponse(status_code=500, content={
                        "message": "Full transcript text is missing, cannot generate Pass 1 script.",
                        "input_file": input_path,
                        "transcript_source": transcript_source_message,
                        "transcript_file": predictable_transcript_path
                    })
                # --- End Define full_transcript_text_for_p1 ---
                
                p1_input = VerbatimScriptPass1Input(
                    full_transcript_text=full_transcript_text_for_p1,
                    user_prompt_for_video_theme=gemini_user_prompt_to_use,
                    allow_reordering=app_config.feature_flags.allow_reordering,
                    video_context=video_context
                )
                try:
                    pass1_verbatim_script_content = await asyncio.to_thread(
                        generate_verbatim_script_pass1,
                        p1_input
                    )
                    if not pass1_verbatim_script_content: # Check if generation itself returned empty
                        logger.warning("Pass 1 generation returned empty content. This might lead to downstream issues.")
                        # No explicit return here, let it proceed. An empty script will likely result in no candidate video.
                    else:
                        logger.info(f"Pass 1 script generated successfully. Length: {len(pass1_verbatim_script_content)} chars.")
                except Exception as e_pass1_gen:
                    logger.error(f"Error during Pass 1 verbatim script generation: {e_pass1_gen}", exc_info=True)
                    # Decide if this is fatal. For now, let's try to proceed, though likely no video.
                    # Alternatively, return JSONResponse here.
                    pass1_verbatim_script_content = "" # Ensure it's an empty string to avoid None issues later

            # Save the (potentially reused or newly generated) Pass 1 script content
            # This default save path uses the current run_timestamp. If P1 was reused, its original path is in pass1_verbatim_script_path.
            current_run_pass1_save_path = os.path.join(TRANSCRIPTS_DIR, f"{base_name}_pass1_verbatim_script_{run_timestamp}.txt")
            try:
                with open(current_run_pass1_save_path, "w", encoding="utf-8") as f:
                    f.write(pass1_verbatim_script_content if pass1_verbatim_script_content is not None else "")
                logger.info(f"Pass 1 verbatim script content for this run saved to: {current_run_pass1_save_path}")
                if pass1_verbatim_script_path != current_run_pass1_save_path and os.path.exists(pass1_verbatim_script_path):
                    logger.info(f"(Note: This run is based on Pass 1 content from: {pass1_verbatim_script_path})")
                else: # pass1_verbatim_script_path would be the same as current_run_pass1_save_path if newly generated
                    pass1_verbatim_script_path = current_run_pass1_save_path # Ensure it points to the saved file for this run if new

            except Exception as e_save_p1:
                logger.error(f"Failed to save Pass 1 verbatim script for this run to {current_run_pass1_save_path}: {e_save_p1}", exc_info=True)

            if not pass1_verbatim_script_content:
                logger.error("Pass 1 verbatim script is empty. Cannot proceed with matching quotes or video generation.")
                return JSONResponse(status_code=500, content={
                    "message": "Pass 1 script generation resulted in empty content. Cannot proceed.",
                    "input_file": input_path,
                    "transcript_source": transcript_source_message,
                    "pass1_script_path": pass1_verbatim_script_path # Path where empty script was attempted to be saved
                })
            
            # Split the Pass 1 script into a list of quotes - This should always happen AFTER content is finalized.
            parsed_pass1_quotes = [quote.strip() for quote in pass1_verbatim_script_content.splitlines() if quote.strip()]

            # --- Attempt to Reuse Candidate Video (NEW BLOCK) ---
            candidate_video_path: Optional[str] = None
            candidate_video_was_reused = False

            if reuse_latest_candidate_video:
                logger.info(f"Attempting to reuse latest candidate video for base name: {base_name}")
                # Suffix for candidate video is typically .mp4, ensure find_most_recent_file handles this or is generic enough
                latest_candidate_video_file = find_most_recent_file(PROCESSED_DIR, base_name, "candidate_video", ".mp4")

                if latest_candidate_video_file:
                    logger.info(f"Found most recent candidate video to reuse: {latest_candidate_video_file}")
                    candidate_video_path = latest_candidate_video_file
                    candidate_video_was_reused = True

                    # Attempt to load the Pass 1 script corresponding to this reused candidate video
                    cand_basename = os.path.basename(latest_candidate_video_file)
                    # Regex for candidate_video_YYYYMMDD_HHMMSS.mp4
                    cand_match = re.search(rf"{re.escape(base_name)}_candidate_video_(\d{{8}}_\d{{6}})\.mp4$", cand_basename)
                    if cand_match:
                        associated_timestamp = cand_match.group(1)
                        corresponding_p1_filename = f"{base_name}_pass1_verbatim_script_{associated_timestamp}.txt"
                        corresponding_p1_path = os.path.join(TRANSCRIPTS_DIR, corresponding_p1_filename)
                        logger.info(f"Looking for corresponding Pass 1 script: {corresponding_p1_path}")

                        if os.path.exists(corresponding_p1_path):
                            logger.info(f"Found corresponding Pass 1 script for reused candidate video: {corresponding_p1_path}")
                            try:
                                with open(corresponding_p1_path, "r", encoding="utf-8") as f_reused_p1:
                                    pass1_verbatim_script_content = f_reused_p1.read() # Overwrite previous P1 content
                                    parsed_pass1_quotes = [q.strip() for q in pass1_verbatim_script_content.splitlines() if q.strip()] # Reparse
                                    pass1_verbatim_script_path = corresponding_p1_path # Update active P1 path
                                logger.info(f"Successfully loaded and parsed corresponding Pass 1 script. {len(parsed_pass1_quotes)} quotes. This P1 content will now be used.")
                            except Exception as e_read_corr_p1:
                                logger.warning(f"Failed to read corresponding Pass 1 script '{corresponding_p1_path}': {e_read_corr_p1}. Continuing with initially loaded/generated P1 script content.", exc_info=True)
                        else:
                            logger.warning(f"Corresponding Pass 1 script '{corresponding_p1_path}' not found. Reused candidate video may not align with current Pass 1 script content.")
                    else:
                        logger.warning(f"Could not extract timestamp from reused candidate video filename '{cand_basename}' to find its corresponding Pass 1 script.")
                else:
                    logger.info(f"No existing candidate video file found to reuse for '{base_name}'. Will generate a new one.")
                    candidate_video_was_reused = False # Ensure it's false if not found
            
            # --- Match Quotes to Timestamps (EDL for Candidate Video Generation) ---
            # This step uses the finalized parsed_pass1_quotes (either from initial P1 or from P1 tied to reused candidate video)
            # and all_transcript_segments_structured (from the original full video transcript).
            candidate_video_edl: List[Tuple[float, float]] = []
            if not parsed_pass1_quotes:
                logger.warning("No valid quotes parsed from Pass 1 output (after potential candidate video reuse logic). Cannot generate candidate video EDL.")
            else:
                logger.info(f"Attempting to match {len(parsed_pass1_quotes)} Pass 1 quotes to full transcript for candidate video EDL...")
                try:
                    if not all_transcript_segments_structured:
                        logger.error("Full transcript segments are not available for matching. Cannot create candidate video EDL.")
                    else:
                        candidate_video_edl = await asyncio.to_thread(
                            match_quotes_to_timestamps,
                            parsed_pass1_quotes,
                            all_transcript_segments_structured
                        )
                        logger.info(f"Match_quotes_to_timestamps for candidate EDL returned {len(candidate_video_edl)} entries.")
                except Exception as e_match_quotes:
                    logger.error(f"Error during match_quotes_to_timestamps for candidate EDL: {e_match_quotes}", exc_info=True)

            # --- Generate Candidate Video File (if not reused) ---
            if not candidate_video_was_reused:
                logger.info("--- Starting Intermediate Step 2: Generate New Candidate Video ---")
                # Define candidate_video_path for new video
                candidate_video_path = os.path.join(PROCESSED_DIR, f"{base_name}_candidate_video_{run_timestamp}.mp4")
                try:
                    if not candidate_video_edl: 
                        raise ValueError("Cannot generate candidate video with an empty EDL from Pass 1 matching.")
                    # ... (rest of the existing candidate video generation logic, using candidate_video_edl and saving to candidate_video_path)
                    logger.info(f"Attempting to create candidate video with {len(candidate_video_edl)} clips from EDL using ffmpeg_utils.cut_and_concatenate...")
                    formatted_candidate_edl_for_ffmpeg = []
                    for start_time, end_time in candidate_video_edl:
                        # Do NOT apply user padding here – we want to keep the raw timestamps.
                        if start_time < end_time:
                            formatted_candidate_edl_for_ffmpeg.append({'start': start_time, 'end': end_time})
                        else:
                            logger.warning(
                                f"Skipping invalid segment for candidate video EDL: start={start_time}, end={end_time}.")
                    
                    if not formatted_candidate_edl_for_ffmpeg:
                        raise ValueError("No valid segments in EDL after formatting for candidate video generation.")

                    # --- Merge overlapping or adjacent (after padding) segments to avoid duplicate footage ---
                    formatted_candidate_edl_for_ffmpeg.sort(key=lambda seg: seg['start'])
                    merged_segments: List[Dict[str, float]] = []
                    for seg in formatted_candidate_edl_for_ffmpeg:
                        if not merged_segments:
                            merged_segments.append(seg)
                            continue

                        last = merged_segments[-1]
                        # If the current segment overlaps or directly abuts the previous (<= 0.05 s gap), merge them
                        if seg['start'] <= last['end'] + 1e-3:  # using small epsilon to account for float rounding
                            last['end'] = max(last['end'], seg['end'])
                        else:
                            merged_segments.append(seg)

                    # Optional: visual analysis to extend clips if needed
                    vision_service = GeminiVisionService(api_key=app_config.gemini_config.api_key)
                    analysed_segments: List[Dict[str, float]] = []
                    first_vision_error_logged = False  # Log full traceback only once to keep console readable
                    for clip_idx, seg in enumerate(merged_segments, start=1):
                        try:
                            # --- create temporary clip for vision analysis ---
                            tmp_fd, tmp_clip_path = tempfile.mkstemp(suffix=".mp4", prefix="vision_clip_")
                            os.close(tmp_fd)  # We'll use ffmpeg to write to this path

                            # Build a clip for vision that includes user-specified context padding
                            vision_clip_start = max(0.0, seg['start'] - pad_before_seconds)
                            vision_clip_end   = seg['end'] + pad_after_seconds

                            # Use ffmpeg copy to produce this clip quickly (no re-encode)
                            ffmpeg_cmd = [
                                "ffmpeg", "-nostdin", "-y",
                                "-ss", str(vision_clip_start),
                                "-to", str(vision_clip_end),
                                "-i", input_path,
                                "-c", "copy",
                                tmp_clip_path,
                            ]

                            # Run ffmpeg synchronously in a thread to stay compatible with Windows' Proactor loop
                            proc_result = await asyncio.to_thread(
                                subprocess.run,
                                ffmpeg_cmd,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                check=False,
                            )

                            if proc_result.returncode != 0:
                                logger.warning(f"FFmpeg failed to make temp clip {tmp_clip_path}. Skipping vision analysis for this segment.")
                                extend_before = extend_after = 0.0
                            else:
                                extend_before, extend_after = await vision_service.analyse_clip(
                                    clip_path=tmp_clip_path,
                                    transcript_slice=None
                                )
                                logger.info(
                                    f"[Vision] Clip {clip_idx}/{len(merged_segments)} "
                                    f"{seg['start']:.2f}-{seg['end']:.2f}s -> "
                                    f"extend_before={extend_before:.2f}, extend_after={extend_after:.2f}"
                                )
                            # Clean up temp clip file
                            try:
                                os.remove(tmp_clip_path)
                            except OSError:
                                pass
                        except Exception as e_vis:
                            if not first_vision_error_logged:
                                logger.error(
                                    f"Vision analysis failed for seg {seg}: {e_vis}. Traceback follows.",
                                    exc_info=True,
                                )
                                first_vision_error_logged = True
                            else:
                                logger.warning(
                                    f"Vision analysis failed for seg {seg}: {e_vis}. (Full traceback logged earlier). Using original padding."
                                )
                            extend_before, extend_after = 0.0, 0.0

                        # Apply user padding *only if* Vision decided to extend the clip.
                        if extend_before > 0 or extend_after > 0:
                            # Vision decided to include some of the context. Only include the amount it asked for.
                            new_start = max(0.0, seg['start'] - extend_before)
                            new_end   = seg['end'] + extend_after
                        else:
                            # Vision kept the clip as-is – no user padding in final render.
                            new_start = seg['start']
                            new_end   = seg['end']

                        if new_start < new_end:
                            analysed_segments.append({'start': new_start, 'end': new_end})
                        else:
                            analysed_segments.append(seg)  # fallback

                    # Re-merge after potential extension
                    analysed_segments.sort(key=lambda s: s['start'])
                    final_segments: List[Dict[str, float]] = []
                    for seg in analysed_segments:
                        if not final_segments:
                            final_segments.append(seg)
                            continue
                        last = final_segments[-1]
                        if seg['start'] <= last['end'] + 1e-3:
                            last['end'] = max(last['end'], seg['end'])
                        else:
                            final_segments.append(seg)

                    formatted_candidate_edl_for_ffmpeg = final_segments
                    logger.info(f"Segment count after vision extension & re-merge: {len(formatted_candidate_edl_for_ffmpeg)}")

                    await asyncio.to_thread(
                        cut_and_concatenate,
                        input_path, 
                        formatted_candidate_edl_for_ffmpeg,
                        candidate_video_path
                    )
                    logger.info(f"New candidate video successfully generated and saved to: {candidate_video_path}")
                except Exception as e_candidate_video:
                    logger.error(f"Error generating new candidate video: {e_candidate_video}", exc_info=True)
                    candidate_video_path = None # Ensure path is None on error for the check below
            else:
                logger.info(f"Using reused candidate video: {candidate_video_path}")

            # --- Check if Candidate Video is available (either reused or newly generated) ---
            if not candidate_video_path or not os.path.exists(candidate_video_path):
                logger.error(f"Candidate video file is not available (path: {candidate_video_path}). Cannot proceed.")
                return JSONResponse(status_code=500, content={
                    "message": "Failed to generate candidate video. Cannot proceed.",
                    "input_file": input_path,
                    "transcript_source": transcript_source_message,
                    "verbatim_script_file": pass1_verbatim_script_path, # Assuming pass1_verbatim_script_path is defined
                    "app_config_used": app_config.model_dump()
                })
            logger.info(f"Candidate video is available at: {candidate_video_path}")

            # --- Intermediate Step 3: Transcribe Candidate Video (if available) ---
            logger.info(f"--- Starting Intermediate Step 3: Transcribe Candidate Video ({candidate_video_path}) ---")
            candidate_video_transcript_segments: List[Dict[str, Any]] = [] # Ensure initialized
            candidate_video_transcript_path: Optional[str] = None

            if candidate_video_path and os.path.exists(candidate_video_path):
                # Use a distinct name for candidate transcript files
                candidate_video_basename = os.path.splitext(os.path.basename(candidate_video_path))[0]
                # Path for the full JSON output from whisper_utils for the candidate video
                predictable_cand_transcript_json_path = os.path.join(TRANSCRIPTS_DIR, f"{candidate_video_basename}_full_transcription.json")
                # Path for just the structured segments list (for easier reload or review)
                candidate_segments_save_path = os.path.join(TRANSCRIPTS_DIR, f"{candidate_video_basename}_structured_segments_{run_timestamp}.json")

                # For candidate video, we likely always want a fresh transcript unless a very specific reuse is implemented
                logger.info(f"Transcribing candidate video: {candidate_video_path}")
                try:
                    cand_transcript_result = await asyncio.to_thread(
                        transcribe_video,
                        video_path=candidate_video_path,
                        model_name=app_config.transcription_config.model_name,
                        language=app_config.transcription_config.language,
                        audio_track=0,
                        silence_duration=app_config.audio_config.min_silence_duration,
                        silence_threshold=app_config.audio_config.silence_threshold,
                        save_speech_audio_path=None,
                    )

                    cand_transcript_data_dict = cand_transcript_result
                    cand_struct_segments = cand_transcript_result.get('segments', []) if cand_transcript_result else []

                    if cand_struct_segments:
                        candidate_video_transcript_segments = cand_struct_segments
                        candidate_video_transcript_path = predictable_cand_transcript_json_path # Path where transcribe_video saved the full data
                        logger.info(f"Candidate video transcribed. Segments: {len(candidate_video_transcript_segments)}. Full transcript at: {candidate_video_transcript_path}")
                        # Save the clean structured segments separately for easier review/debug if needed
                        save_json_to_file(candidate_video_transcript_segments, candidate_segments_save_path)
                        logger.info(f"Candidate video structured segments saved to: {candidate_segments_save_path}")
                    else:
                        logger.error(f"Candidate video transcription resulted in no structured segments. Path: {candidate_video_path}")
                except Exception as e_cand_transcribe:
                    logger.error(f"Error during candidate video transcription: {e_cand_transcribe}", exc_info=True)
                    # candidate_video_transcript_segments remains empty
            else:
                logger.warning("Candidate video path is not valid or file does not exist. Skipping candidate video transcription.")
            
            if not candidate_video_transcript_segments:
                logger.error("Failed to obtain transcript segments for the candidate video. This is required for Pass 2 text matching.")
                # This is a critical issue for the new Pass 2 flow. We might need to return an error if P2 is vital.
                # For now, Pass 2 will be skipped if this is empty, as per logic in Step 4.

            logger.info("--- Finished Intermediate Step 3: Transcribe Candidate Video ---")

            # --- Intermediate Step 4: Refine Video with Multimodal Pass 2 (Text Output Workflow) ---
            logger.info("--- Starting Intermediate Step 4: Refine Video with Multimodal Pass 2 (Text Output) ---")
            pass2_selected_text_segments: List[str] = []
            final_pass2_edl: List[Dict[str, Any]] = [] # This will be the EDL for the *final* video
            pass2_text_output_path: Optional[str] = None # Path for saving P2's text output
            pass2_matched_edl_path: Optional[str] = None # Path for saving the EDL from text matching

            if candidate_video_path and os.path.exists(candidate_video_path):
                logger.info(f"Calling Multimodal Pass 2 with candidate video: {candidate_video_path}")
                try:
                    pass2_selected_text_segments = await asyncio.to_thread(
                        refine_video_with_multimodal_pass2,
                        candidate_video_path=candidate_video_path,
                        user_prompt=gemini_user_prompt_to_use,
                        allow_reordering=app_config.feature_flags.allow_reordering,
                        allow_repetition=app_config.feature_flags.allow_repetition,
                        gemini_api_key=app_config.gemini_config.api_key
                    )
                except Exception as e_pass2_gemini:
                    logger.error(f"Error during Multimodal Pass 2 (refine_video_with_multimodal_pass2) call: {e_pass2_gemini}", exc_info=True)
                    pass2_selected_text_segments = [] # Ensure it's an empty list on error
                
                if pass2_selected_text_segments:
                    logger.info(f"Multimodal Pass 2 returned {len(pass2_selected_text_segments)} selected text segments.")
                    pass2_text_output_path = os.path.join(TRANSCRIPTS_DIR, f"{base_name}_pass2_multimodal_text_output_{run_timestamp}.json")
                    save_json_to_file(pass2_selected_text_segments, pass2_text_output_path)
                    logger.info(f"Multimodal Pass 2 raw text output saved to: {pass2_text_output_path}")

                    # Now, match these text segments to the candidate video's transcript
                    if candidate_video_transcript_segments:
                        logger.info("Matching Pass 2 selected text segments to candidate video transcript timestamps...")
                        similarity_p2_matching = getattr(app_config, 'matching_similarity_threshold_pass2', 80)
                        try:
                            final_pass2_edl = await asyncio.to_thread(
                                match_text_segments_to_transcript_timestamps,
                                selected_text_segments=pass2_selected_text_segments,
                                candidate_transcript_segments=candidate_video_transcript_segments,
                                similarity_threshold=similarity_p2_matching
                            )
                            if final_pass2_edl:
                                logger.info(f"Successfully matched {len(final_pass2_edl)} Pass 2 text segments, forming final EDL.")
                                pass2_matched_edl_path = os.path.join(TRANSCRIPTS_DIR, f"{base_name}_pass2_final_matched_edl_{run_timestamp}.json")
                                save_json_to_file(final_pass2_edl, pass2_matched_edl_path)
                                logger.info(f"Final EDL from Pass 2 text matching saved to: {pass2_matched_edl_path}")
                            else:
                                logger.warning("match_text_segments_to_transcript_timestamps returned an empty EDL after Pass 2 text selection.")
                                # final_pass2_edl is already an empty list if this path is taken
                        except Exception as e_match_p2_text:
                            logger.error(f"Error during match_text_segments_to_transcript_timestamps: {e_match_p2_text}", exc_info=True)
                            final_pass2_edl = [] # Ensure empty on error
                    else:
                        logger.error("Candidate video transcript segments are not available. Cannot match Pass 2 text output to get timestamps.")
                        # final_pass2_edl remains empty
                else:
                    logger.warning("Multimodal Pass 2 returned no selected text segments. No final EDL will be generated from Pass 2.")
                    # final_pass2_edl remains empty
            else:
                logger.warning("Candidate video not available. Skipping Multimodal Pass 2 and subsequent text matching.")
                # pass2_selected_text_segments and final_pass2_edl remain empty lists
            
            logger.info("--- Finished Intermediate Step 4 ---")

            # --- Intermediate Step 5: Final Video Assembly from Pass 2 EDL ---
            logger.info("--- Starting Intermediate Step 5: Final Video Assembly from Pass 2 EDL ---")
            final_multimodal_video_path = None
            if final_pass2_edl: # Only attempt if EDL for ffmpeg has segments
                final_multimodal_video_path = os.path.join(PROCESSED_DIR, f"{base_name}_final_multimodal_{run_timestamp}{os.path.splitext(file.filename)[1]}")
                try:
                    logger.info(f"Assembling final video from {len(final_pass2_edl)} segments using candidate video '{candidate_video_path}' as source.")
                    await asyncio.to_thread(
                        cut_and_concatenate,
                        candidate_video_path, # Source is the candidate video
                        final_pass2_edl, # Use the processed EDL for ffmpeg
                        final_multimodal_video_path,
                        audio_track=0 # Candidate video's audio
                    )
                    logger.info(f"Final multimodal video successfully assembled and saved to: {final_multimodal_video_path}")
                except Exception as e_final_assembly:
                    logger.error(f"Error during final video assembly: {e_final_assembly}", exc_info=True)
                    final_multimodal_video_path = None # Ensure path is None on error
            elif not final_pass2_edl: # Empty EDL
                 logger.info("Skipping final video assembly as Pass 2 EDL is empty.")


            # --- Update Response Payload ---
            # The main response payload is constructed at the end of the main try block.
            # We need to ensure the variables used there are correctly set.
            # `final_video_path` in the main response should now point to `final_multimodal_video_path`.
            # We'll create a new dictionary here for clarity for the new pipeline success.
            
            processing_message = "New multimodal pipeline completed."
            if not final_multimodal_video_path and not final_pass2_edl: # Pass 2 EDL was empty
                processing_message = "Multimodal pipeline completed, but Pass 2 selected no segments. No final video produced."
            elif not final_multimodal_video_path and final_pass2_edl : # Pass 2 EDL had segments, but assembly failed
                 processing_message = "Multimodal pipeline completed, but final video assembly failed."


            logger.info(f"New multimodal pipeline processing finished for {file.filename}.")
            return JSONResponse(status_code=200, content={
                "message": processing_message,
                "input_file": input_path,
                "original_full_transcript_file": predictable_transcript_path,
                "pass1_verbatim_script_file": pass1_verbatim_script_path,
                "candidate_video_file": candidate_video_path,
                # "candidate_video_transcript_file": candidate_transcript_path if candidate_transcript_data else None, # REMOVED / Set to None
                "candidate_video_transcript_file": None, # Explicitly None
                "pass2_multimodal_text_output_file": pass2_text_output_path if pass2_selected_text_segments else None,
                "final_video_file": final_multimodal_video_path, # This is the main output
                "app_config_used": app_config.model_dump()
            })
            # --- End of New Pipeline ---

            # The old code below this point will now be effectively bypassed by the return statement above.
            # !!! === THE REMAINDER OF THE FILE IS THE OLD LOGIC AND WILL BE BYPASSED === !!!
            # !!! === IT WILL NEED SIGNIFICANT REFACTORING FOR THE NEW PIPELINE === !!!


        # --- Secondary Word-Level Transcription (if applicable) ---
        segments_for_editing_strategy_input = segments_from_gemini_or_full_transcript
        
        attempt_word_level_processing = (
            app_config.feature_flags.enable_phrase_level_editing and
            segments_from_gemini_or_full_transcript and # Segments are available (either fresh or reused)
            not (gemini_output_reused and reused_data_is_already_augmented) # And not already augmented via reuse
        )

        if attempt_word_level_processing:
            logger.info("Attempting secondary word-level transcription and augmentation for segments because 'enable_phrase_level_editing' is True and segments are not already augmented via reuse.")
            augmented_coarse_segments = []
            word_level_temp_dir = tempfile.mkdtemp(prefix=f"{base_name}_word_audio_")
            logger.info(f"Created temporary directory for word-level audio segments: {word_level_temp_dir}")
            
            # Ensure coarse segments have an ID for Pass 3 to reference
            temp_segments_with_ids = []
            for idx, seg_dict in enumerate(segments_from_gemini_or_full_transcript):
                new_seg_dict = dict(seg_dict) # Work with a copy
                if 'id' not in new_seg_dict:
                    new_seg_dict['id'] = f"coarse_seg_{idx}"
                temp_segments_with_ids.append(new_seg_dict)
            
            # Iterate over the list that now has IDs
            for i, original_segment_dict in enumerate(temp_segments_with_ids):
                current_coarse_segment = dict(original_segment_dict) 
                original_segment_start = current_coarse_segment.get('start')
                original_segment_end = current_coarse_segment.get('end')

                if original_segment_start is None or original_segment_end is None or original_segment_end <= original_segment_start:
                    logger.warning(f"Skipping segment {i} for word-level transcription due to invalid/missing timestamps: {current_coarse_segment}")
                    augmented_coarse_segments.append(current_coarse_segment) # Add as-is
                    continue

                temp_audio_segment_path = os.path.join(word_level_temp_dir, f"segment_{i}_audio.wav")
                
                extraction_successful = await asyncio.to_thread(
                    extract_audio_segment,
                    input_video_path=input_path, 
                    start_time=original_segment_start,
                    end_time=original_segment_end,
                    output_audio_path=temp_audio_segment_path,
                    audio_track_index=audio_track 
                )

                if extraction_successful and os.path.exists(temp_audio_segment_path):
                    try:
                        words_in_segment = await asyncio.to_thread(
                            transcribe_audio_with_word_timestamps,
                            audio_path=temp_audio_segment_path,
                            language=app_config.transcription_config.language,
                            model_name=app_config.transcription_config.model_name 
                        )
                        
                        # Timestamps from transcribe_audio_with_word_timestamps are relative to the start of temp_audio_segment_path,
                        # which is exactly what we want for them to be relative to original_segment_start.
                        current_coarse_segment['word_level_details'] = words_in_segment
                        logger.debug(f"Segment {i}: Augmented with {len(words_in_segment)} words.")
                    except Exception as e_word_transcribe:
                        logger.error(f"Error during word-level transcription for segment {i} ({temp_audio_segment_path}): {e_word_transcribe}", exc_info=True)
                        current_coarse_segment['word_level_details'] = [] # Add empty list on failure
                else:
                    logger.warning(f"Failed to extract audio for segment {i}. No word-level details will be added.")
                    current_coarse_segment['word_level_details'] = []
                
                augmented_coarse_segments.append(current_coarse_segment)
            
            if any(seg.get('word_level_details') for seg in augmented_coarse_segments):
                logger.info(f"Successfully augmented coarse segments with word-level details.")
                segments_for_editing_strategy_input = augmented_coarse_segments
                # Save augmented coarse_segments for debugging/review if needed
                augmented_output_path = os.path.join(TRANSCRIPTS_DIR, f"{base_name}_augmented_segments_{run_timestamp}.json")
                try:
                    with open(augmented_output_path, "w", encoding="utf-8") as f_aug_dump:
                        json.dump(augmented_coarse_segments, f_aug_dump, ensure_ascii=False, indent=2)
                    logger.info(f"Saved augmented coarse segments (with word details) to: {augmented_output_path}")
                except Exception as e_dump:
                    logger.error(f"Failed to save augmented coarse segments: {e_dump}")
            else:
                logger.warning("Word-level transcription failed to augment any segments. Falling back to segment-level input for editing strategy.")
                # segments_for_editing_strategy_input remains segments_from_gemini_or_full_transcript
            
            # Clean up temporary directory for word audio segments
            try:
                shutil.rmtree(word_level_temp_dir)
                logger.info(f"Cleaned up temporary directory: {word_level_temp_dir}")
            except Exception as e_cleanup:
                logger.error(f"Error cleaning up temp directory {word_level_temp_dir}: {e_cleanup}")
        else:
            if gemini_output_reused and reused_data_is_already_augmented and app_config.feature_flags.enable_phrase_level_editing:
                logger.info("Skipping secondary word-level transcription: Reused data is already augmented and phrase-level editing is enabled.")
                # segments_for_editing_strategy_input is already set to the reused, augmented data.
            elif not app_config.feature_flags.enable_phrase_level_editing:
                logger.info("Skipping secondary word-level transcription: 'enable_phrase_level_editing' is False.")
            elif not segments_from_gemini_or_full_transcript:
                logger.info("Skipping secondary word-level transcription: No segments available.")
            else: # Catch-all for other reasons, though covered by attempt_word_level_processing
                logger.info("Skipping secondary word-level transcription (reason not explicitly listed or already covered by attempt_word_level_processing logic).") 
            # --- End Secondary Word-Level Transcription ---

        # --- Apply Editing Strategy ---
        # print(f"[MAIN DEBUG] Type of app_config.editing_style JUST BEFORE .value access: {type(app_config.editing_style)}, value: {app_config.editing_style}", flush=True)
        
        # app_config.editing_style will be a string (e.g., "custom") due to Pydantic V2 behavior with str Enums.
        logger.info(f"Applying editing strategy: {app_config.editing_style}") 
        
        # Compare the string value from app_config with the string value of the Enum member.
        if app_config.editing_style == EditingStyle.CUSTOM.value:
            current_editing_strategy = CustomEditingStrategy(app_config.feature_flags)
        # Default to CHRONOLOGICAL for safety, also covers if it's EditingStyle.CHRONOLOGICAL.value
        else: 
            current_editing_strategy = ChronologicalEditingStrategy(app_config.feature_flags)
        
        logger.info(f"Using editing strategy: {type(current_editing_strategy).__name__}")

        # The input to the strategy is now 'segments_for_editing_strategy_input'
        # which could be word-level or segment-level segments
        segments_after_strategy = current_editing_strategy.process_segments(
            segments=list(segments_for_editing_strategy_input), # Pass a copy
            narrative_outline=verbatim_script_text if 'verbatim_script_text' in locals() else "",
            user_prompt=gemini_user_prompt_to_use
        )
        logger.info(f"Editing strategy produced {len(segments_after_strategy)} segments for final video cut.")
        # --- End Apply Editing Strategy ---

        # 3. Cut and concatenate video
        final_video_path = None
        if produce_video and segments_after_strategy is not None and len(segments_after_strategy) > 0: # Use segments_after_strategy
            logger.info(f"Starting video processing using {len(segments_after_strategy)} segments...")
            try:
                output_video_filename = f"processed_{base_name}_{run_timestamp}{os.path.splitext(file.filename)[1]}"
                final_video_path = os.path.join(PROCESSED_DIR, output_video_filename)
                await asyncio.to_thread( # Assuming cut_and_concatenate is sync
                    cut_and_concatenate, 
                    input_path, 
                    segments_after_strategy, # Use segments_after_strategy
                    final_video_path, 
                    audio_track
                )
                logger.info(f"Video processing complete. Output saved to: {final_video_path}")
            except Exception as e:
                logger.error(f"Video processing failed: {str(e)}", exc_info=True)
                final_video_path = None
        elif not produce_video:
            logger.info("Skipping video production (produce_video=False).")
        else:
            logger.info("Skipping video production (no relevant segments to process or segments_for_video_cut is None).")

        logger.info(f"Processing complete for {file.filename}! {transcript_source_message}")
        response_payload = {
            "message": f"Processing complete! {transcript_source_message}",
            "original_file": file.filename,
            "processed_video_file": final_video_path,
            "reusable_transcript_file": predictable_transcript_path, 
            "gemini_output_file": gemini_processed_segments_path, 
            "reusable_speech_only_audio_file": predictable_speech_audio_path if app_config.transcription_config.save_speech_audio and os.path.exists(str(predictable_speech_audio_path)) else None # Use AppConfig
        }
        # Also include narrative_outline_path in response if it exists
        if 'narrative_outline_path' in locals() and narrative_outline_path and os.path.exists(narrative_outline_path):
            response_payload["narrative_outline_file"] = narrative_outline_path
            
        return JSONResponse(response_payload)

    except Exception as e:
        logger.error(f"Critical error during processing of {file.filename}: {str(e)}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": f"Error processing file: {str(e)}"}) 

@app.get("/test-preview/{filename}")
async def test_preview(filename: str):
    """Test endpoint to check if a preview file exists"""
    file_path = os.path.join(PREVIEW_DIR, filename)
    if os.path.exists(file_path):
        return {"exists": True, "size": os.path.getsize(file_path), "path": file_path}
    else:
        return {"exists": False, "path": file_path}