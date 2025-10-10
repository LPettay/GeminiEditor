"""
Video Processing Service - Modular service for video analysis, transcript generation, and clip extraction.
This service can be easily swapped out with different processing backends.
"""

import os
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class TranscriptWord:
    """Individual word in transcript with timing."""
    word: str
    start: float
    end: float
    confidence: float

@dataclass
class TranscriptSegment:
    """Transcript segment with words and timing."""
    id: str
    start: float
    end: float
    text: str
    words: List[TranscriptWord]
    confidence: float
    speaker: Optional[str] = None

@dataclass
class ProcessingResult:
    """Result of video processing."""
    transcript_segments: List[TranscriptSegment]
    video_metadata: Dict[str, Any]
    processing_time: float
    success: bool
    error_message: Optional[str] = None

class VideoProcessingService:
    """Service for processing videos to extract transcripts and clips."""
    
    @classmethod
    async def process_video_for_editing(
        cls,
        video_id: str,
        video_path: str,
        on_progress: Optional[callable] = None
    ) -> ProcessingResult:
        """
        Process a video to generate transcript and prepare for editing.
        
        Args:
            video_id: Unique identifier for the video
            video_path: Path to the video file
            on_progress: Optional callback for progress updates
            
        Returns:
            ProcessingResult with transcript segments and metadata
        """
        try:
            if on_progress:
                on_progress(0, "Starting video analysis...")
            
            # Generate transcript using existing Whisper implementation
            transcript_data = await cls._generate_transcript(video_path, on_progress)
            
            if on_progress:
                on_progress(80, "Processing transcript segments...")
            
            # Convert to our structured format
            segments = cls._convert_to_transcript_segments(transcript_data)
            
            # Extract video metadata
            metadata = await cls._extract_video_metadata(video_path)
            
            if on_progress:
                on_progress(100, "Processing complete!")
            
            return ProcessingResult(
                transcript_segments=segments,
                video_metadata=metadata,
                processing_time=0,  # We don't track processing time yet
                success=True
            )
            
        except Exception as e:
            logger.error(f"Video processing failed: {str(e)}")
            return ProcessingResult(
                transcript_segments=[],
                video_metadata={},
                processing_time=0,
                success=False,
                error_message=str(e)
            )
    
    @classmethod
    async def _generate_transcript(cls, video_path: str, on_progress: Optional[callable] = None) -> Dict[str, Any]:
        """Generate transcript using existing Whisper implementation."""
        # Import and use existing whisper utilities
        from app.whisper_utils import transcribe_audio_with_word_timestamps
        
        if on_progress:
            on_progress(10, "Extracting audio...")
        
        # Extract audio for transcription
        audio_path = await cls._extract_audio(video_path)
        
        if on_progress:
            on_progress(30, "Transcribing audio...")
        
        # Transcribe with word-level timestamps
        transcript_result = await asyncio.to_thread(
            transcribe_audio_with_word_timestamps,
            audio_path=audio_path,
            language="en",  # Default to English, could be made configurable
            model_name="base"  # Default to base model, could be made configurable
        )
        
        # Clean up temporary audio file
        if os.path.exists(audio_path):
            os.unlink(audio_path)
        
        if on_progress:
            on_progress(70, "Processing transcript data...")
        
        return transcript_result
    
    @classmethod
    async def _extract_audio(cls, video_path: str) -> str:
        """Extract audio from video for transcription."""
        import tempfile
        import subprocess
        
        # Create temporary audio file
        temp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_audio.close()
        
        # Extract audio using ffmpeg
        cmd = [
            'ffmpeg', '-i', video_path,
            '-vn',  # No video
            '-acodec', 'pcm_s16le',  # Audio codec
            '-ar', '16000',  # Sample rate
            '-ac', '1',  # Mono
            '-y',  # Overwrite output file
            temp_audio.name
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Audio extraction failed: {result.stderr}")
        
        return temp_audio.name
    
    @classmethod
    def _convert_to_transcript_segments(cls, words_data: List[Dict[str, Any]]) -> List[TranscriptSegment]:
        """Convert words data to structured segments with intelligent boundary detection."""
        if not words_data:
            return []
        
        # Convert word data to TranscriptWord objects
        all_words = []
        for word_data in words_data:
            all_words.append(TranscriptWord(
                word=word_data['word'],
                start=word_data['start'],
                end=word_data['end'],
                confidence=word_data.get('probability', 1.0)
            ))
        
        if not all_words:
            return []
        
        # Segment strategy: Create segments based on time intervals and natural boundaries
        segments = []
        segment_words = []
        current_segment_start = all_words[0].start
        max_segment_duration = 15.0  # Maximum 15 seconds per segment
        max_words_per_segment = 50   # Maximum words per segment
        
        for i, word in enumerate(all_words):
            segment_words.append(word)
            
            # Check if we should end the current segment
            should_end_segment = False
            segment_duration = word.end - current_segment_start
            
            # End segment if:
            # 1. Maximum duration reached
            # 2. Maximum word count reached
            # 3. Natural sentence boundary (period, exclamation, question mark)
            # 4. Significant pause (gap > 1.5 seconds)
            # 5. Last word
            if (segment_duration >= max_segment_duration or 
                len(segment_words) >= max_words_per_segment or
                cls._is_sentence_ending(word.word) or
                cls._has_significant_pause(word, all_words, i) or
                i == len(all_words) - 1):
                should_end_segment = True
            
            if should_end_segment and segment_words:
                # Create segment from current words
                segment_start = segment_words[0].start
                segment_end = segment_words[-1].end
                segment_text = ' '.join(w.word for w in segment_words)
                segment_confidence = sum(w.confidence for w in segment_words) / len(segment_words)
                
                segment = TranscriptSegment(
                    id=f"segment_{len(segments)}",
                    start=segment_start,
                    end=segment_end,
                    text=segment_text.strip(),
                    words=segment_words.copy(),
                    confidence=segment_confidence,
                    speaker=None
                )
                segments.append(segment)
                
                # Reset for next segment
                segment_words = []
                if i < len(all_words) - 1:
                    current_segment_start = all_words[i + 1].start
        
        return segments
    
    @classmethod
    def _is_sentence_ending(cls, word: str) -> bool:
        """Check if a word indicates the end of a sentence."""
        # Remove punctuation and check if it's a sentence ending
        clean_word = word.strip('.,!?;:')
        return (word.endswith('.') or word.endswith('!') or word.endswith('?') or 
                word.endswith(';') or word.endswith(':'))
    
    @classmethod
    def _has_significant_pause(cls, current_word: TranscriptWord, all_words: List[TranscriptWord], current_index: int) -> bool:
        """Check if there's a significant pause after the current word."""
        if current_index >= len(all_words) - 1:
            return False
        
        next_word = all_words[current_index + 1]
        gap = next_word.start - current_word.end
        
        # Consider a gap > 1.5 seconds as a significant pause
        return gap > 1.5
    
    @classmethod
    async def _extract_video_metadata(cls, video_path: str) -> Dict[str, Any]:
        """Extract video metadata using ffprobe."""
        import subprocess
        import json
        
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"Failed to extract metadata: {result.stderr}")
            return {}
        
        try:
            metadata = json.loads(result.stdout)
            return {
                'duration': float(metadata.get('format', {}).get('duration', 0)),
                'width': None,
                'height': None,
                'fps': None,
                'codec': None
            }
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse metadata: {e}")
            return {}
    
    @classmethod
    def create_clip_from_segment(
        cls,
        segment: TranscriptSegment,
        source_video_path: str,
        output_dir: str
    ) -> str:
        """Create a clip file from a transcript segment."""
        import subprocess
        import uuid
        
        # Generate unique filename for clip
        clip_filename = f"clip_{uuid.uuid4().hex[:8]}_{int(segment.start)}_{int(segment.end)}.mp4"
        clip_path = os.path.join(output_dir, clip_filename)
        
        # Extract clip using ffmpeg
        cmd = [
            'ffmpeg', '-i', source_video_path,
            '-ss', str(segment.start),
            '-t', str(segment.end - segment.start),
            '-c', 'copy',  # Copy without re-encoding
            '-avoid_negative_ts', 'make_zero',
            '-y',  # Overwrite output file
            clip_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Clip extraction failed: {result.stderr}")
        
        return clip_path


# Convenience functions for easy integration
async def process_video_for_editing(
    video_id: str,
    video_path: str,
    on_progress: Optional[callable] = None
) -> ProcessingResult:
    """Convenience function to process a video for editing."""
    return await VideoProcessingService.process_video_for_editing(
        video_id, video_path, on_progress
    )

def create_clip_from_segment(
    segment: TranscriptSegment,
    source_video_path: str,
    output_dir: str
) -> str:
    """Convenience function to create a clip from a segment."""
    return VideoProcessingService.create_clip_from_segment(
        segment, source_video_path, output_dir
    )
