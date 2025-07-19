import whisper
import os
import ffmpeg
import re
import logging
import time
import sys
import subprocess
import shutil
import tempfile
import contextlib
import torch
import json
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Context manager to temporarily suppress stderr (and stdout if needed)
@contextlib.contextmanager
def suppress_output(stdout=False, stderr=True):
    """A context manager to temporarily suppress stdout and/or stderr."""
    devnull = open(os.devnull, 'w')
    old_stdout, old_stderr = sys.stdout, sys.stderr
    try:
        if stdout:
            sys.stdout = devnull
        if stderr:
            sys.stderr = devnull
        yield
    finally:
        if stdout:
            sys.stdout = old_stdout
        if stderr:
            sys.stderr = old_stderr
        devnull.close()

def clean_transcript_text(text):
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove common transcription artifacts
    text = re.sub(r'\[.*?\]', '', text)  # Remove [music], [applause], etc.
    text = re.sub(r'\(.*?\)', '', text)  # Remove (unintelligible), etc.
    # Fix common transcription errors
    text = re.sub(r'\b(um|uh|er|ah)\b', '', text, flags=re.IGNORECASE)
    # Remove repeated words
    text = re.sub(r'\b(\w+)(\s+\1\b)+', r'\1', text)
    return text.strip()

def detect_silences(audio_path, threshold=-50, min_duration=0.2):
    """
    Detect silent regions in audio file.
    Returns list of (start, end) timestamps for each silence.
    """
    logger.info(f"Detecting silences in {audio_path}")
    logger.info(f"Using threshold: {threshold}dB, min duration: {min_duration}s")
    
    cmd = [
        'ffmpeg', '-i', audio_path,
        '-af', f'silencedetect=noise={threshold}dB:d={min_duration}',
        '-f', 'null', '-'
    ]
    
    process = subprocess.run(cmd, capture_output=True, text=True)
    if process.returncode != 0:
        # Log the full FFmpeg output for debugging
        logger.error(f"FFmpeg error during silence detection. Command: {' '.join(cmd)}")
        logger.error(f"FFmpeg stderr: {process.stderr}")
        raise RuntimeError(f"Failed to detect silences. FFmpeg stderr: {process.stderr}")
    
    silences = []
    current_start = None
    
    for line in process.stderr.split('\n'):
        if 'silence_start' in line:
            try:
                start_str = line.split('silence_start: ')[1].split(' |')[0]
                current_start = float(start_str)
            except (IndexError, ValueError) as e:
                logger.warning(f"Could not parse silence_start from line: '{line}'. Error: {e}")
                current_start = None # Reset if parsing fails
        elif 'silence_end' in line and current_start is not None:
            try:
                end_str = line.split('silence_end: ')[1].split(' |')[0]
                silence_end = float(end_str)
                # Ensure silence_end is after current_start
                if silence_end > current_start:
                    silences.append((current_start, silence_end))
                else:
                    logger.warning(f"Detected silence_end <= silence_start. Line: '{line}'. Start: {current_start}, End: {silence_end}. Skipping this range.")
            except (IndexError, ValueError) as e:
                logger.warning(f"Could not parse silence_end from line: '{line}'. Error: {e}")
            finally:
                current_start = None # Reset for the next pair
    
    # Log summary
    logger.info(f"Found {len(silences)} silence regions")
    if silences:
        total_silence = sum(end - start for start, end in silences)
        logger.info(f"Total silence duration: {total_silence:.2f}s")
    
    return silences

def get_speech_segments(video_or_audio_path, silences):
    """
    Get list of speech segments (non-silent parts) from video or audio file.
    Returns list of (start, end) timestamps for each speech segment.
    """
    try:
        probe = ffmpeg.probe(video_or_audio_path)
        duration = float(probe['format']['duration'])
    except ffmpeg.Error as e:
        logger.error(f"Failed to probe duration for {video_or_audio_path}. FFmpeg error: {e.stderr.decode('utf8')}")
        raise RuntimeError(f"Could not get duration of {video_or_audio_path}")

    speech_segments = []
    current_time = 0.0
    
    # Sort silences by start time to ensure correct processing order
    sorted_silences = sorted(silences, key=lambda x: x[0])
    
    for silence_start, silence_end in sorted_silences:
        # Ensure silence times are within media duration and logical
        silence_start = max(0, min(silence_start, duration))
        silence_end = max(silence_start, min(silence_end, duration))

        if silence_start > current_time:
            # Add speech segment before the current silence
            speech_segments.append((current_time, silence_start))
        current_time = max(current_time, silence_end) # Move current_time to the end of the current silence
    
    # Add the final speech segment if any part remains after the last silence
    if current_time < duration:
        speech_segments.append((current_time, duration))
    
    # Filter out zero or negative duration segments that might occur due to edge cases
    speech_segments = [(s, e) for s, e in speech_segments if e > s]

    logger.info(f"Found {len(speech_segments)} speech segments for {video_or_audio_path}")
    if speech_segments:
        total_speech = sum(end - start for start, end in speech_segments)
        logger.info(f"Total speech duration from segments: {total_speech:.2f}s (Original duration: {duration:.2f}s)")
    
    return speech_segments

def get_audio_metadata(input_path):
    """Get audio metadata from the input file."""
    logger.info(f"Getting audio metadata from {input_path}")
    probe = ffmpeg.probe(input_path)
    
    # Find the audio stream
    audio_stream = None
    for stream in probe['streams']:
        if stream['codec_type'] == 'audio':
            audio_stream = stream
            break
    
    if not audio_stream:
        raise ValueError("No audio stream found in the input file")
    
    # Get audio metadata
    metadata = {
        'codec_name': audio_stream.get('codec_name', 'pcm_s16le'),
        'channels': int(audio_stream.get('channels', 2)),
        'sample_rate': int(audio_stream.get('sample_rate', 48000)),
        'bits_per_sample': int(audio_stream.get('bits_per_sample', 16)),
        'bit_rate': int(audio_stream.get('bit_rate', 192000))
    }
    
    logger.info("Audio metadata:")
    logger.info(f"  Codec: {metadata['codec_name']}")
    logger.info(f"  Channels: {metadata['channels']}")
    logger.info(f"  Sample Rate: {metadata['sample_rate']} Hz")
    logger.info(f"  Bits per Sample: {metadata['bits_per_sample']}")
    logger.info(f"  Bit Rate: {metadata['bit_rate']} bps")
    
    return metadata

def preprocess_audio(input_path, output_path, silence_duration=0.2):
    """
    Preprocess audio by detecting silences and creating a mapping for video editing.
    Preserves original audio quality while creating a mapping of silence regions.
    
    Args:
        input_path: Path to input audio file
        output_path: Path to output audio file
        silence_duration: Minimum silence duration in seconds (default: 0.2)
    
    Returns:
        tuple: (output_path, timestamp_map) - The path to the processed audio file and the timestamp mapping
    """
    logger.info(f"Preprocessing audio from {input_path}")
    logger.info(f"Using silence duration: {silence_duration}s")
    
    # Get audio metadata
    audio_metadata = get_audio_metadata(input_path)
    
    # Get silence map first
    timestamp_map, silence_ranges = get_silence_map(input_path)
    
    try:
        # Instead of removing silences, we'll just apply basic audio enhancement
        # while preserving the original audio quality
        cmd = [
            'ffmpeg', '-i', input_path,
            '-af', 'highpass=f=200,lowpass=f=3000,volume=1.5',  # Subtle enhancement
            '-acodec', audio_metadata['codec_name'],
            '-ac', str(audio_metadata['channels']),
            '-ar', str(audio_metadata['sample_rate']),
            '-b:a', str(audio_metadata['bit_rate']),
            '-y',  # Overwrite output file
            output_path
        ]
        
        logger.info("Applying audio preprocessing...")
        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode != 0:
            logger.error(f"FFmpeg error: {process.stderr}")
            raise RuntimeError("Failed to process audio")
        
        # Verify the output file
        output_info = ffmpeg.probe(output_path)
        if 'duration' in output_info['format']:
            output_duration = float(output_info['format']['duration'])
        else:
            output_duration = 0
            for stream in output_info['streams']:
                if stream['codec_type'] == 'audio':
                    if 'duration' in stream:
                        output_duration = float(stream['duration'])
                        break
                    elif 'duration_ts' in stream and 'time_base' in stream:
                        time_base = stream['time_base'].split('/')
                        output_duration = float(stream['duration_ts']) / float(time_base[0]) / float(time_base[1])
                        break
    
    except Exception as e:
        logger.error(f"Error in preprocess_audio: {e}")
        raise

    return output_path, timestamp_map

def transcribe_video(video_path, model_name="base", language="en", audio_track=0, 
                     silence_duration=0.2, silence_threshold=-50, 
                     save_speech_audio_path=None):
    """
    Transcribe video using Whisper model.
    Only transcribes non-silent parts of the video.
    Optionally saves a concatenated audio file of only speech segments.
    
    Args:
        video_path: Path to input video file
        model_name: Whisper model name (default: "base")
        language: Language code (default: "en")
        audio_track: The audio track to use (default: 0)
        silence_duration: Minimum silence duration for detection (default: 0.2)
        silence_threshold: Silence threshold in dB for detection (default: -50dB)
        save_speech_audio_path: Optional path to save the concatenated speech-only audio. (default: None)
    
    Returns:
        dict: Transcription result with segments mapped to original video timestamps, 
              and a list of speech_segments used for video editing.
    """
    logger.info(f"Starting transcription of {video_path} using model {model_name}, lang {language}, audio track {audio_track}")
    
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    main_temp_dir = tempfile.mkdtemp(prefix=f"{base_name}_")
    temp_audio_path = os.path.join(main_temp_dir, "extracted_audio.wav")

    try:
        # 1. Extract full audio from video
        # First, check what audio tracks are available
        probe_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_streams', '-print_format', 'json', video_path]
        try:
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            audio_streams = json.loads(probe_result.stdout).get('streams', [])
            num_audio_tracks = len(audio_streams)
            
            logger.info(f"Found {num_audio_tracks} audio tracks in {video_path}")
            for i, stream in enumerate(audio_streams):
                logger.info(f"  Track {i}: {stream.get('codec_name', 'unknown')} - {stream.get('tags', {}).get('language', 'unknown language')}")
            
            # Validate audio track selection
            if audio_track >= num_audio_tracks:
                logger.warning(f"Requested audio track {audio_track} but only {num_audio_tracks} tracks available. Using track 0.")
                audio_track = 0
            
        except Exception as e:
            logger.warning(f"Could not probe audio tracks: {e}. Using requested track {audio_track}.")
            num_audio_tracks = 1  # Assume at least one track exists
        
        logger.info(f"Extracting audio track {audio_track} from {video_path} to {temp_audio_path}")
        cmd_extract = [
            'ffmpeg', '-i', video_path,
            '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
            '-map', f'0:a:{audio_track}', '-y', temp_audio_path
        ]
        subprocess.run(cmd_extract, check=True, capture_output=True, text=True)
        logger.info("Audio extraction complete.")

        # 2. Detect silences
        silences = detect_silences(temp_audio_path, threshold=silence_threshold, min_duration=silence_duration)
        
        # 3. Get speech segments (these are the unpadded, precise segments)
        speech_segments_timestamps = get_speech_segments(video_path, silences)

        # 3b. Save concatenated speech-only audio if path provided
        if save_speech_audio_path and speech_segments_timestamps:
            logger.info(f"Saving concatenated speech-only audio to: {save_speech_audio_path}")
            speech_segment_files_dir = os.path.join(main_temp_dir, "speech_segments_for_concat")
            os.makedirs(speech_segment_files_dir, exist_ok=True)
            segment_file_paths = []
            concat_list_path = os.path.join(speech_segment_files_dir, "concat_list.txt")

            try:
                for i, (start, end) in enumerate(speech_segments_timestamps):
                    seg_file_out = os.path.join(speech_segment_files_dir, f"speech_{i}.wav")
                    cmd_extract_speech_seg = [
                        'ffmpeg', '-i', temp_audio_path,
                        '-ss', str(start), '-to', str(end),
                        '-acodec', 'pcm_s16le', # Keep it as WAV
                        '-y', seg_file_out
                    ]
                    subprocess.run(cmd_extract_speech_seg, check=True, capture_output=True, text=True)
                    segment_file_paths.append(seg_file_out)
                
                with open(concat_list_path, 'w') as f_concat:
                    for f_path in segment_file_paths:
                        # FFmpeg concat demuxer needs paths to be escaped/quoted if they contain special chars.
                        # Simpler to use relative paths if possible, or ensure paths are safe.
                        # For now, using direct paths; ensure they don't have problematic characters or use `ffmpeg.input(filename=...)`
                        f_concat.write(f"file '{os.path.relpath(f_path, speech_segment_files_dir).replace(os.sep, '/')}'\n")

                cmd_concat_speech = [
                    'ffmpeg', '-f', 'concat', '-safe', '0', '-i', concat_list_path,
                    '-acodec', 'pcm_s16le', # Output as WAV
                    '-y', save_speech_audio_path
                ]
                subprocess.run(cmd_concat_speech, check=True, capture_output=True, text=True)
                logger.info("Successfully saved speech-only audio.")
            except Exception as e_speech_audio:
                logger.error(f"Could not save speech-only audio: {e_speech_audio}", exc_info=True)
            finally:
                # Clean up the temp dir used for speech segment concatenation
                if os.path.exists(speech_segment_files_dir):
                     shutil.rmtree(speech_segment_files_dir)
        elif save_speech_audio_path and not speech_segments_timestamps:
            logger.warning(f"No speech segments found; cannot save speech-only audio to {save_speech_audio_path}")

        # 4. Determine device and Load Whisper model
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading Whisper model: {model_name} onto device: {device}")
        model = whisper.load_model(model_name, device=device)
        logger.info(f"Whisper model {model_name} loaded successfully on {device}.")
        
        # 5. Transcribe each speech segment individually
        if not speech_segments_timestamps:
            logger.warning(f"No speech segments found in {video_path} after silence detection. Transcription will be empty.")
            return {
                'text': '',
                'segments': [],
                'language': language,
                'speech_segments': [] 
            }

        num_speech_segments = len(speech_segments_timestamps)
        logger.info(f"Starting transcription of {num_speech_segments} speech segments...")
        all_transcribed_segments = []
        full_text_parts = []
        padding_duration = 0.15

        try:
            probe_extracted_audio = ffmpeg.probe(temp_audio_path)
            total_extracted_audio_duration = float(probe_extracted_audio['format']['duration'])
        except ffmpeg.Error as e:
            logger.error(f"Failed to probe duration for temporary audio {temp_audio_path}. FFmpeg error: {e.stderr.decode('utf8')}")
            total_extracted_audio_duration = float('inf') 

        for i, (unpadded_seg_start, unpadded_seg_end) in enumerate(speech_segments_timestamps):
            progress_message = f"\rTranscribing speech segments: {i+1}/{num_speech_segments} processed..."
            sys.stdout.write(progress_message)
            sys.stdout.flush()

            segment_duration = unpadded_seg_end - unpadded_seg_start
            if segment_duration <= 0.1: 
                logger.debug(f"Skipping speech segment {i+1}/{num_speech_segments} (duration {segment_duration:.2f}s) as it is too short.")
                continue

            whisper_infer_start = max(0.0, unpadded_seg_start - padding_duration)
            whisper_infer_end = min(total_extracted_audio_duration, unpadded_seg_end + padding_duration)
            
            if whisper_infer_end <= whisper_infer_start:
                logger.debug(f"Skipping speech segment {i+1}/{num_speech_segments} after padding resulted in zero/negative duration.")
                continue

            logger.debug(f"Processing speech segment {i+1}/{num_speech_segments}: Original ({unpadded_seg_start:.2f}s - {unpadded_seg_end:.2f}s), Padded for Whisper ({whisper_infer_start:.2f}s - {whisper_infer_end:.2f}s)")
            segment_audio_path = os.path.join(main_temp_dir, f"segment_{i}.wav")
            
            try:
                cmd_segment_extract = [
                    'ffmpeg', '-i', temp_audio_path,
                    '-ss', str(whisper_infer_start), 
                    '-to', str(whisper_infer_end),
                    '-acodec', 'pcm_s16le', 
                    '-y',
                    segment_audio_path
                ]
                subprocess.run(cmd_segment_extract, check=True, capture_output=True, text=True)

                with suppress_output(stderr=True, stdout=False):
                    result = model.transcribe(segment_audio_path, language=language, verbose=False)
                
                for whisper_seg in result.get('segments', []):
                    original_seg_start_time = whisper_infer_start + whisper_seg['start']
                    original_seg_end_time = whisper_infer_start + whisper_seg['end']
                    adjusted_segment = {
                        'start': original_seg_start_time,
                        'end': original_seg_end_time,
                        'text': whisper_seg['text'].strip(),
                        'avg_logprob': whisper_seg.get('avg_logprob'),
                        'no_speech_prob': whisper_seg.get('no_speech_prob')
                    }
                    all_transcribed_segments.append(adjusted_segment)
                    full_text_parts.append(whisper_seg['text'].strip())
                logger.debug(f"Segment {i+1} transcribed. Text: '{result.get('text', '').strip()[:50]}...'")

            except Exception as e_seg:
                logger.error(f"\nError processing segment {i+1} ({unpadded_seg_start:.2f}-{unpadded_seg_end:.2f}): {e_seg}")
            finally:
                if os.path.exists(segment_audio_path):
                    os.remove(segment_audio_path)
        
        sys.stdout.write("\r" + " " * len(progress_message) + "\r")
        sys.stdout.flush()
        logger.info(f"Transcription of {num_speech_segments} speech segments complete. Total text length: {len(' '.join(full_text_parts))} chars.")

        final_text = ' '.join(full_text_parts)
        final_result = {
            'text': final_text,
            'segments': all_transcribed_segments,
            'language': language,
            'speech_segments': speech_segments_timestamps
        }
        
        return final_result
        
    except Exception as e:
        logger.error(f"Error during transcription process for {video_path}: {e}", exc_info=True)
        raise
    finally:
        if os.path.exists(main_temp_dir):
            shutil.rmtree(main_temp_dir)
            logger.info(f"Cleaned up main temporary directory: {main_temp_dir}")

def transcribe_audio_with_word_timestamps(audio_path: str, language: str, model_name: str, device: str = None) -> List[Dict[str, Any]]:
    """
    Transcribes the given audio file using Whisper and returns word-level timestamps.

    Args:
        audio_path: Path to the audio file to transcribe.
        language: Language code for transcription (e.g., "en").
        model_name: Name of the Whisper model to use (e.g., "base", "small").
        device: The device to run the model on ("cuda" or "cpu"). Autodetects if None.

    Returns:
        A list of dictionaries, where each dictionary represents a word and contains:
        - "word": The transcribed word (string).
        - "start": The start time of the word in seconds (float).
        - "end": The end time of the word in seconds (float).
        - "probability": The probability of the word (float, via whisperx compatibility if available).
                         For standard whisper, this might be less direct or might need to be inferred.
                         Whisper's standard output gives segment-level probabilities.
                         If direct word probability isn't available, we might omit or estimate.
    """
    logger.info(f"Starting word-level transcription for: {audio_path} using model {model_name}, lang {language}")
    
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    
    try:
        logger.debug(f"Loading Whisper model: {model_name} onto device: {device} for word-level transcription.")
        # Ensure model is loaded on the correct device each time, or manage a global model instance carefully.
        # For simplicity here, loading it per call.
        model = whisper.load_model(model_name, device=device)
        logger.debug(f"Whisper model {model_name} loaded for word-level transcription.")

        # Transcribe with word_timestamps=True
        # Note: Standard whisper.transcribe() returns segment-level data even with word_timestamps=True.
        # The word timestamps are nested within each segment. We need to extract and flatten them.
        # Also, verbose=False can hide progress bars that might be undesirable for library use.
        # However, for debugging, verbose=True might be useful temporarily.
        result = model.transcribe(audio_path, language=language, word_timestamps=True, verbose=False)
        
        all_words = []
        if result and 'segments' in result:
            for segment in result['segments']:
                if 'words' in segment:
                    for word_data in segment['words']:
                        # word_data from whisper is typically: {'word': str, 'start': float, 'end': float, 'probability': float}
                        # We should ensure the keys match our desired output or adapt if different.
                        # Standard whisper might not directly give 'probability' per word in this structure,
                        # it's more common in whisperx or aligned outputs.
                        # Let's check what standard whisper provides for 'words'.
                        # Defaulting to what is usually available. Adding a placeholder for probability.
                        all_words.append({
                            "word": word_data['word'].strip(), # Clean up any leading/trailing spaces from the word itself
                            "start": round(word_data['start'], 3),
                            "end": round(word_data['end'], 3),
                            # "probability": round(word_data.get('probability', 0.0), 3) # Safely get probability if available
                        })
            logger.info(f"Word-level transcription complete. Extracted {len(all_words)} words from {audio_path}.")
        else:
            logger.warning(f"No segments or words found in transcription result for {audio_path}.")
            
        return all_words

    except FileNotFoundError:
        logger.error(f"Audio file not found for word-level transcription: {audio_path}")
        raise
    except Exception as e:
        logger.error(f"Error during word-level transcription for {audio_path}: {e}", exc_info=True)
        # Consider if specific errors should be handled differently or re-raised.
        raise