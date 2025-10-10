"""
Video Segmentation Service - Splits videos into clips aligned with transcript segments.
"""

import os
import uuid
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from app.ffmpeg_utils import cut_video_segment
from app.dao import TranscriptSegmentDAO
from app.models import TranscriptSegment

logger = logging.getLogger(__name__)

@dataclass
class VideoClip:
    """Represents a video clip segment."""
    id: str
    segment_id: str
    source_video_id: str
    start_time: float
    end_time: float
    file_path: str
    duration: float
    order_index: int = 0  # For rearranging

@dataclass
class SegmentationResult:
    """Result of video segmentation process."""
    clips: List[VideoClip]
    success: bool
    error_message: Optional[str] = None
    processing_time: float = 0.0

class VideoSegmentationService:
    """
    Service for segmenting videos into clips based on transcript segments.
    """
    
    def __init__(self, clips_dir: str = "clips"):
        self.clips_dir = Path(clips_dir)
        self.clips_dir.mkdir(exist_ok=True)
    
    async def segment_video_for_editing(
        self,
        source_video_id: str,
        video_path: str,
        on_progress: Optional[callable] = None
    ) -> SegmentationResult:
        """
        Segment a video into clips based on transcript segments.
        """
        logger.info(f"Starting video segmentation for video {source_video_id}")
        
        try:
            if on_progress:
                on_progress(10, "Loading transcript segments...")
            
            # Get transcript segments from database
            from app.database import SessionLocal
            db = SessionLocal()
            try:
                segments = TranscriptSegmentDAO.get_by_video(db, source_video_id)
                logger.info(f"Database query for video {source_video_id} returned {len(segments) if segments else 0} segments")
                
                if not segments:
                    # Check if the video exists in the database
                    from app.dao import SourceVideoDAO
                    video = SourceVideoDAO.get_by_id(db, source_video_id)
                    if not video:
                        return SegmentationResult(
                            clips=[],
                            success=False,
                            error_message=f"Video {source_video_id} not found in database"
                        )
                    else:
                        return SegmentationResult(
                            clips=[],
                            success=False,
                            error_message=f"No transcript segments found for video {source_video_id}. Please generate a transcript first by clicking 'Generate Transcript for Editing'."
                        )
                
                logger.info(f"Found {len(segments)} transcript segments")
                
                if on_progress:
                    on_progress(20, f"Processing {len(segments)} segments...")
                
                clips = []
                for i, segment in enumerate(segments):
                    if on_progress:
                        progress = 20 + (i / len(segments)) * 70
                        on_progress(int(progress), f"Creating clip {i+1}/{len(segments)}...")
                    
                    try:
                        # Create clip with timeout
                        clip = await asyncio.wait_for(
                            self._create_clip(
                                source_video_id=source_video_id,
                                segment=segment,
                                video_path=video_path,
                                order_index=i
                            ),
                            timeout=60.0  # 60 second timeout per clip
                        )
                        clips.append(clip)
                        logger.info(f"Successfully created clip {i+1}/{len(segments)}: {clip.id}")
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout creating clip {i+1}/{len(segments)} for segment {segment.id}")
                        # Continue with other clips instead of failing completely
                        continue
                    except Exception as e:
                        logger.error(f"Error creating clip {i+1}/{len(segments)} for segment {segment.id}: {str(e)}")
                        # Continue with other clips instead of failing completely
                        continue
                
                if on_progress:
                    on_progress(100, "Video segmentation complete!")
                
                return SegmentationResult(
                    clips=clips,
                    success=True,
                    processing_time=0.0  # We don't track time yet
                )
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Video segmentation failed: {str(e)}")
            return SegmentationResult(
                clips=[],
                success=False,
                error_message=str(e)
            )
    
    async def _create_clip(
        self,
        source_video_id: str,
        segment: TranscriptSegment,
        video_path: str,
        order_index: int
    ) -> VideoClip:
        """Create a single video clip from a transcript segment."""
        
        # Generate unique clip filename
        clip_id = str(uuid.uuid4())
        clip_filename = f"clip_{source_video_id}_{segment.id}_{clip_id}.mp4"
        clip_path = self.clips_dir / clip_filename
        
        logger.info(f"Creating clip {clip_id} from {segment.start_time}s to {segment.end_time}s")
        
        # Skip very short segments that might cause FFmpeg issues
        duration = segment.end_time - segment.start_time
        if duration < 0.1:  # Skip segments shorter than 0.1 seconds
            logger.warning(f"Skipping very short segment: {duration}s")
            raise Exception(f"Segment too short: {duration}s")
        
        # Use ffmpeg to cut the video segment
        result = await asyncio.to_thread(
            cut_video_segment,
            video_path,
            str(clip_path),
            segment.start_time,
            segment.end_time
        )
        
        if result.returncode != 0:
            raise Exception(f"Failed to create clip: {result.stderr}")
        
        # Calculate clip duration
        duration = segment.end_time - segment.start_time
        
        return VideoClip(
            id=clip_id,
            segment_id=segment.id,
            source_video_id=source_video_id,
            start_time=segment.start_time,
            end_time=segment.end_time,
            file_path=str(clip_path),
            duration=duration,
            order_index=order_index
        )
    
    def get_clip_stream_url(self, clip_id: str, project_id: str) -> str:
        """Get the streaming URL for a video clip."""
        return f"/api/projects/{project_id}/clips/{clip_id}/play"
    
    def delete_clips_for_video(self, source_video_id: str):
        """Delete all clips for a source video."""
        clip_files = self.clips_dir.glob(f"clip_{source_video_id}_*")
        for clip_file in clip_files:
            try:
                clip_file.unlink()
                logger.info(f"Deleted clip file: {clip_file}")
            except Exception as e:
                logger.error(f"Failed to delete clip file {clip_file}: {e}")

# Singleton instance
video_segmentation_service = VideoSegmentationService()
