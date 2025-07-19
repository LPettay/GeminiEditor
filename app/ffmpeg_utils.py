import ffmpeg
import os
import tempfile
import shutil
import logging
import sys
import subprocess # Import subprocess

# Setup logger for this module
logger = logging.getLogger(__name__)

def cut_and_concatenate(file_path, segments, output_path, audio_track=0):
    temp_dir = tempfile.mkdtemp()
    segment_files = []
    padding_duration = 0.15  # Seconds to pad each segment's end, experiment with this value
    # min_gap_between_segments is no longer needed as we don't do inter-segment adjustment here

    total_segments_to_process = len(segments)
    if total_segments_to_process == 0:
        logger.info("No segments to process for video cutting.")
        # Create an empty file or handle as per desired behavior for no segments
        # For now, let it proceed, which will result in an empty concat_list.txt
        # and ffmpeg will likely error on an empty concat list. 
        # A more robust solution would be to touch output_path or return early.
        pass 

    logger.info(f"Starting video segment extraction for {total_segments_to_process} segments.")
    progress_message_template = "Extracting video segment {i_plus_1} of {total} (Time: {start_time:.2f}s - {end_time:.2f}s)..."
    last_progress_message_len = 0

    try:
        # 1. Extract each segment
        for i, seg in enumerate(segments):
            # Progress update using sys.stdout.write
            # Using .get for start/end in case segment dict structure varies unexpectedly
            current_start = seg.get('start', 0.0)
            current_end = seg.get('end', 0.0)
            progress_message = progress_message_template.format(
                i_plus_1=i + 1, 
                total=total_segments_to_process, 
                start_time=current_start, 
                end_time=current_end
            )
            # Clear previous message by padding with spaces
            sys.stdout.write(f"\r{progress_message}{' ' * max(0, last_progress_message_len - len(progress_message))}")
            sys.stdout.flush()
            last_progress_message_len = len(progress_message)

            seg_file = os.path.join(temp_dir, f'segment_{i}.mp4')

            current_segment_start_time = seg['start']
            # Calculate the target end time for the cut, including padding at the end of this segment's content
            target_cut_end_time = seg['end'] + padding_duration 

            # Ensure segment duration is positive after considering padding.
            # This handles cases where seg['end'] might be <= seg['start'] or padding is negative.
            if target_cut_end_time <= current_segment_start_time:
                logger.warning(f"Segment {i+1} (Original: {seg['start']:.2f}s-{seg['end']:.2f}s) has non-positive duration after padding ({target_cut_end_time:.2f}s). Attempting to use original end time.")
                target_cut_end_time = seg['end'] # Try with original end time
                if target_cut_end_time <= current_segment_start_time:
                    logger.warning(f"Segment {i+1} still has non-positive duration ({target_cut_end_time:.2f}s). Using minimal 0.1s duration from start_time.")
                    target_cut_end_time = current_segment_start_time + 0.1 # Default to a minimal positive duration
            
            # Create input stream. Audio track selection relies on ffmpeg's default behavior (usually main mix).
            # The audio_track parameter of this function is NOT used for this cutting part.
            input_ffmpeg = ffmpeg.input(file_path, ss=current_segment_start_time, to=target_cut_end_time)
            video_stream = input_ffmpeg.video
            audio_stream = input_ffmpeg.audio # Takes default audio track(s)
            
            # 'ss' and 'to' on the input should apply to both video and audio, 
            # so separate 'atrim' might not be strictly necessary if 'to' is precise enough.
            # However, keeping atrim can ensure audio duration matches video if there are subtleties.
            # For simplicity and assuming 'to' is effective for both, we can omit atrim here initially.
            # If audio/video sync issues arise with padding, re-evaluate atrim with duration: (target_cut_end_time - current_segment_start_time)

            stream = ffmpeg.output(video_stream, audio_stream,
                                 seg_file,
                                 vcodec='libx264', 
                                 acodec='aac',
                                 # preset='fast', # Optional: consider for speed
                                 loglevel='error')
            ffmpeg.run(stream, overwrite_output=True)
            segment_files.append(seg_file)

        # Clear the progress line after the loop
        if total_segments_to_process > 0:
            sys.stdout.write(f"\r{' ' * last_progress_message_len}\r")
            sys.stdout.flush()

        logger.info(f"All {total_segments_to_process} video segments extracted. Starting concatenation.")
        # 2. Create concat list file
        concat_list = os.path.join(temp_dir, 'concat_list.txt')
        with open(concat_list, 'w') as f:
            for seg_file in segment_files:
                safe_path = seg_file.replace('\\', '/')
                f.write(f"file '{safe_path}'\n")

        # 3. Concatenate segments
        stream = ffmpeg.input(concat_list, format='concat', safe=0)
        stream = ffmpeg.output(stream, 
                             output_path,
                             vcodec='libx264', 
                             acodec='aac',
                             loglevel='error')
        ffmpeg.run(stream, overwrite_output=True)
        logger.info(f"Video concatenation complete. Output: {output_path}")
        return output_path
    finally:
        # Always clean up the temporary directory
        try:
            shutil.rmtree(temp_dir)
            logger.debug(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary directory {temp_dir}: {e}")

def extract_audio_segment(input_video_path: str, start_time: float, end_time: float, output_audio_path: str, audio_track_index: int = 0) -> bool:
    """
    Extracts a specific audio segment from a video file and saves it as a WAV file using a direct FFmpeg command.

    Args:
        input_video_path: Path to the input video file.
        start_time: Start time of the segment to extract (in seconds).
        end_time: End time of the segment to extract (in seconds).
        output_audio_path: Path to save the extracted WAV audio file.
        audio_track_index: The index of the audio track to extract (default 0).

    Returns:
        True if extraction was successful, False otherwise.
    """
    logger.info(f"Extracting audio segment from {input_video_path} (Track {audio_track_index}): {start_time:.2f}s - {end_time:.2f}s -> {output_audio_path} using subprocess")
    duration = round(end_time - start_time, 3) # Calculate duration, round to avoid precision issues

    if duration <= 0:
        logger.warning(f"Cannot extract audio segment: duration is zero or negative ({duration:.3f}s). Skipping.")
        return False
    
    # Ensure output directory exists (though tempfile should handle it for word-level audio)
    output_dir = os.path.dirname(output_audio_path)
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e_mkdir:
            logger.error(f"Failed to create directory {output_dir} for audio segment: {e_mkdir}")
            return False

    # Construct the FFmpeg command
    # Using -nostdin to prevent hanging if ffmpeg expects input on stdin
    # Using -y to overwrite output files without asking
    command = [
        'ffmpeg',
        '-nostdin',
        '-y',
        '-i', input_video_path,
        '-ss', str(start_time),
        '-t', str(duration),
        '-map', f'0:a:{audio_track_index}', # Map specific audio track from first input (0)
        '-acodec', 'pcm_s16le',
        '-ar', '16000',
        '-ac', '1',
        output_audio_path
    ]

    logger.debug(f"Executing FFmpeg command: {' '.join(command)}")

    try:
        # stderr=subprocess.PIPE will capture FFmpeg's error messages
        # text=True decodes stderr as text
        # check=True will raise CalledProcessError if FFmpeg returns a non-zero exit code
        result = subprocess.run(command, capture_output=True, text=True, check=False) # Set check=False to inspect stderr manually

        if result.returncode == 0:
            logger.info(f"Audio segment extracted successfully: {output_audio_path}")
            return True
        else:
            # Log FFmpeg's stderr output for debugging
            logger.error(f"FFmpeg error during audio segment extraction for {output_audio_path} (return code {result.returncode}):")
            logger.error(f"FFmpeg stdout: {result.stdout.strip()}")
            logger.error(f"FFmpeg stderr: {result.stderr.strip()}")
            # Clean up partially created file if error occurs
            if os.path.exists(output_audio_path):
                try:
                    os.remove(output_audio_path)
                except OSError as oe:
                    logger.warning(f"Could not remove partially created audio segment {output_audio_path} after error: {oe}")
            return False

    except FileNotFoundError:
        logger.error(f"FFmpeg command not found. Please ensure FFmpeg is installed and in your system's PATH.")
        return False
    except Exception as e:
        logger.error(f"Unexpected Python error during audio segment extraction for {output_audio_path}: {str(e)}", exc_info=True)
        if os.path.exists(output_audio_path):
            try:
                os.remove(output_audio_path)
            except OSError as oe:
                logger.warning(f"Could not remove partially created audio segment {output_audio_path} after error: {oe}")
        return False