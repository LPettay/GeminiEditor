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
    padding_duration = 0.0  # Disable padding to prevent audio overlap issues
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
            
            # Use subprocess with FFmpeg commands for proper audio track selection
            duration = target_cut_end_time - current_segment_start_time
            
            cmd = [
                'ffmpeg', '-nostdin', '-y',
                '-ss', str(current_segment_start_time),
                '-i', file_path,
                '-t', str(duration),
                '-map', '0:v:0',  # Map video stream
                '-map', '0:a:0',  # Map all audio tracks
                '-map', '0:a:1',
                '-map', '0:a:2',
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-loglevel', 'error',
                seg_file
            ]
            
            logger.debug(f"Extracting segment {i+1}: {current_segment_start_time:.2f}s - {target_cut_end_time:.2f}s (track {audio_track})")
            subprocess.run(cmd, check=True, capture_output=True, text=True)
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


def cut_video_segment(input_video_path: str, output_video_path: str, start_time: float, end_time: float) -> subprocess.CompletedProcess:
    """
    Cut a single segment from a video file using ffmpeg.
    
    Args:
        input_video_path: Path to the input video file
        output_video_path: Path where the cut segment will be saved
        start_time: Start time in seconds
        end_time: End time in seconds
    
    Returns:
        subprocess.CompletedProcess: Result of the ffmpeg command
    """
    duration = end_time - start_time
    
    logger.info(f"Cutting video segment: {start_time}s to {end_time}s (duration: {duration}s)")
    logger.info(f"Input: {input_video_path}")
    logger.info(f"Output: {output_video_path}")
    
    try:
        # Use ffmpeg to cut the video segment
        cmd = [
            'ffmpeg',
            '-i', input_video_path,
            '-ss', str(start_time),
            '-t', str(duration),
            '-c', 'copy',  # Copy streams without re-encoding for speed
            '-avoid_negative_ts', 'make_zero',
            '-y',  # Overwrite output file
            output_video_path
        ]
        
        logger.info(f"Running ffmpeg command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout per clip (much shorter)
        )
        
        if result.returncode == 0:
            logger.info(f"Successfully created video segment: {output_video_path}")
        else:
            logger.error(f"FFmpeg failed with return code {result.returncode}")
            logger.error(f"FFmpeg stderr: {result.stderr}")
            
        return result
        
    except subprocess.TimeoutExpired:
        logger.error(f"FFmpeg timed out after 30 seconds for segment {start_time}s-{end_time}s")
        # Return a failed result
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=124,  # Timeout return code
            stdout="",
            stderr="FFmpeg timed out after 30 seconds"
        )
    except Exception as e:
        logger.error(f"Unexpected error during video segment cutting: {str(e)}")
        return subprocess.CompletedProcess(
            args=cmd if 'cmd' in locals() else [],
            returncode=1,
            stdout="",
            stderr=str(e)
        )