from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
import os
import shutil
import json
import logging
import sys
import time
from enum import Enum
import torch # Import torch for startup check
import asyncio # Added for running sync Gemini functions in thread pool
from typing import Optional, List
import glob # For finding files
import re # For parsing timestamps from filenames

# Changed import for new Gemini functions
from .gemini import generate_narrative_outline, select_segments_for_narrative 
from .whisper_utils import transcribe_video, transcribe_audio_with_word_timestamps
from .ffmpeg_utils import cut_and_concatenate, extract_audio_segment
import tempfile # For managing temporary directories for audio segments

# --- Import New Config and Editing Strategy ---
from app.config import (
    AppConfig,
    EditingStyle,
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

# Configure logging to output to both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',  # Simplified format
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
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
os.makedirs(PROCESSED_AUDIO_DIR, exist_ok=True)

# Define an Enum for Whisper model choices
# class WhisperModel(str, Enum): # No longer needed here, will pass model name as string
#     \"\"\"Available Whisper model sizes for transcription.\"\"\"
#     tiny = "tiny"
#     base = "base"
#     small = "small"
#     medium = "medium"
#     large = "large"
#     large_v2 = "large-v2"
#     large_v3 = "large-v3"

@app.post("/process")
async def process_video(
    file: UploadFile = File(...),
    prompt: str = Form(""), # User prompt for Gemini
    audio_track: int = Form(0, ge=0, description="The 0-indexed audio track to use from the video."),
    produce_video: bool = Form(True),

    # --- Configurable via AppConfig ---
    # Editing Style and Flags
    editing_style: EditingStyle = Form(EditingStyle.CHRONOLOGICAL, description="The editing style to apply."),
    enable_phrase_level_editing: bool = Form(False, description="Enable phrase-level editing (secondary word transcription and Gemini Pass 3)."),
    allow_reordering: bool = Form(False, description="Allow reordering of segments/phrases (if CUSTOM style and phrase editing are selected)."),
    allow_repetition: bool = Form(False, description="Allow repetition of segments/phrases (if CUSTOM style and phrase editing are selected, Gemini controls phrase repetition; otherwise segment-level)."),
    max_segment_repetitions: int = Form(1, ge=1, description="Max times a segment can be repeated (if segment-level repetition is allowed)."),

    # Transcription settings
    whisper_model: str = Form("base", description="Name of the Whisper model to use (e.g., tiny, base, small, medium, large)."),
    transcription_language: str = Form("en", description="Language code for transcription (e.g., en, es, fr)."),
    save_speech_audio_file: bool = Form(False, description="Whether to save a separate speech-only audio file."),

    # Audio processing settings for silence detection
    audio_silence_threshold: float = Form(-50.0, le=0.0, description="Silence threshold in dB (e.g., -50.0). Must be <= 0."),
    audio_min_silence_duration: float = Form(0.2, ge=0.0, description="Minimum silence duration in seconds for detection."),
    
    # Gemini settings
    gemini_chunk_processing_size: int = Form(250, ge=1, description="Number of segments per chunk for Gemini Pass 2 processing."),
    reuse_latest_augmented_segments: bool = Form(False, description="Reuse the most recent existing augmented segment file for this video, skipping prior processing including word-level transcription.")
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
        
        editing_style: The editing style to apply (CHRONOLOGICAL or CUSTOM).
        allow_reordering: If CUSTOM style, allows segments to be reordered.
        allow_repetition: If CUSTOM style, allows segments to be repeated.
        max_segment_repetitions: Max times a segment can be repeated if repetition is allowed.

        whisper_model: Name of the Whisper model for transcription.
        transcription_language: Language code for transcription.
        save_speech_audio_file: Whether to save speech-only audio.

        audio_silence_threshold: Silence threshold for audio processing.
        audio_min_silence_duration: Minimum silence duration for audio processing.
        
        gemini_chunk_processing_size: Segment chunk size for Gemini Pass 2.
        reuse_latest_augmented_segments: Reuse the most recent existing augmented segment file for this video, skipping prior processing including word-level transcription.
    """
    try:
        # --- Construct AppConfig ---
        # print(f"[MAIN DEBUG] Type of editing_style from Form before AppConfig: {type(editing_style)}, value: {editing_style}", flush=True)
        
        app_config = AppConfig(
            editing_style=editing_style,
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
        
        input_path = os.path.join(UPLOAD_DIR, file.filename)
        if not os.path.exists(input_path):
            logger.info(f"Saving uploaded file to: {input_path}")
            with open(input_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            logger.info("File saved successfully")
        else:
            logger.info(f"Using existing file: {input_path}")

        base_name = os.path.splitext(file.filename)[0]

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
            # ---- Pass 1: Generate Narrative Outline ----
            logger.info("Starting Gemini Pass 1: Generating narrative outline.")
            narrative_outline = []
            try:
                # Join all segment texts for Pass 1
                full_transcript_text_for_pass_1 = "\n".join(seg['text'] for seg in all_transcript_segments_structured if seg['text'])
                if not full_transcript_text_for_pass_1.strip():
                    logger.warning("Full transcript text for Gemini Pass 1 is empty. Skipping Pass 1.")
                else:
                    narrative_outline = await asyncio.to_thread(
                        generate_narrative_outline, 
                        full_transcript_text_for_pass_1,
                        gemini_user_prompt_to_use
                    )
                    if narrative_outline:
                        logger.info(f"Gemini Pass 1 complete. Generated {len(narrative_outline)} narrative points.")
                        # Save narrative outline for review
                        narrative_output_filename = f"{base_name}_narrative_outline_{run_timestamp}.json"
                        narrative_outline_path = os.path.join(TRANSCRIPTS_DIR, narrative_output_filename)
                        logger.info(f"Saving narrative outline to: {narrative_outline_path}")
                        with open(narrative_outline_path, "w", encoding="utf-8") as f:
                            json.dump(narrative_outline, f, ensure_ascii=False, indent=2)
                        # gemini_processed_segments_path can store this if no other output is made
                        if not gemini_processed_segments_path: gemini_processed_segments_path = narrative_outline_path
                    else:
                        logger.warning("Gemini Pass 1 returned an empty narrative outline.")
            except Exception as e_pass1:
                logger.error(f"Error during Gemini Pass 1 (narrative generation): {e_pass1}", exc_info=True)
                logger.warning("Proceeding without a narrative outline due to Pass 1 error.")
            
            # ---- Pass 2: Select Segments Based on Narrative ----
            # Use app_config.gemini_config.chunk_size
            logger.info(f"Starting Gemini Pass 2: Selecting segments based on narrative (if available) in chunks of {app_config.gemini_config.chunk_size}.")
            all_selected_segments_from_chunks_pass2 = []
            accumulated_past_text_for_pass2_context = ""
            num_chunks = (len(all_transcript_segments_structured) + app_config.gemini_config.chunk_size - 1) // app_config.gemini_config.chunk_size

            for i in range(0, len(all_transcript_segments_structured), app_config.gemini_config.chunk_size):
                current_chunk_pass2 = all_transcript_segments_structured[i:i + app_config.gemini_config.chunk_size]
                logger.info(f"Processing Gemini Pass 2 chunk {i // app_config.gemini_config.chunk_size + 1} of {num_chunks} ({len(current_chunk_pass2)} segments).")
                
                try:
                    # Pass 2 call using select_segments_for_narrative
                    gemini_filtered_segments_from_chunk = await asyncio.to_thread(
                        select_segments_for_narrative,
                        current_transcript_chunk=current_chunk_pass2,
                        narrative_outline=narrative_outline, # Pass the generated outline
                        user_prompt=gemini_user_prompt_to_use,
                        past_text_context=accumulated_past_text_for_pass2_context
                    )
                    
                    if gemini_filtered_segments_from_chunk:
                        all_selected_segments_from_chunks_pass2.extend(gemini_filtered_segments_from_chunk)
                        logger.info(f"Pass 2 Chunk {i // app_config.gemini_config.chunk_size + 1}: Gemini selected {len(gemini_filtered_segments_from_chunk)} segments.")
                    else:
                        logger.info(f"Pass 2 Chunk {i // app_config.gemini_config.chunk_size + 1}: Gemini selected no segments from this chunk.")

                    chunk_text_content = "\n".join(seg.get('text', '') for seg in current_chunk_pass2 if seg.get('text', '').strip())
                    if chunk_text_content:
                        accumulated_past_text_for_pass2_context += chunk_text_content + "\n\n"

                except Exception as e_chunk_pass2:
                    logger.error(f"Error processing Gemini Pass 2 chunk {i // app_config.gemini_config.chunk_size + 1}: {str(e_chunk_pass2)}", exc_info=True)
                    logger.warning("Skipping this Pass 2 chunk due to error. Selections from this chunk will be lost.")
            
            if all_selected_segments_from_chunks_pass2:
                # These are the segments Gemini *thinks* are good, before applying editing strategy
                segments_from_gemini_or_full_transcript = all_selected_segments_from_chunks_pass2 
                logger.info(f"Gemini Pass 2 complete. Total segments selected by Gemini: {len(segments_from_gemini_or_full_transcript)}.")
                # Save Pass 2 selected segments (if different from narrative outline)
                pass2_output_filename = f"{base_name}_pass2_selected_segments_{run_timestamp}.json"
                gemini_processed_segments_path = os.path.join(TRANSCRIPTS_DIR, pass2_output_filename) # Overwrite/set path for final Gemini output
                logger.info(f"Saving combined Pass 2 Gemini-selected segments to: {gemini_processed_segments_path}")
                with open(gemini_processed_segments_path, "w", encoding="utf-8") as f:
                    json.dump(segments_from_gemini_or_full_transcript, f, ensure_ascii=False, indent=2)
            else:
                logger.warning("Gemini Pass 2 returned no segments. Video will be based on original transcript or Pass 1 outline if video cutting relies on segments.")
                # segments_from_gemini_or_full_transcript remains all_transcript_segments_structured if Pass 2 fails and Pass 1 didn't populate it

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
            narrative_outline=narrative_outline if 'narrative_outline' in locals() else [],
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