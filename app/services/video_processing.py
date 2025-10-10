"""
Video processing service for the new project-based workflow.
Handles transcription, AI analysis, and EDL creation.
"""

import os
import logging
import uuid
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.dao import ProjectDAO, SourceVideoDAO, TranscriptSegmentDAO, EditDAO, EditDecisionDAO
from app.whisper_utils import transcribe_video
from app.gemini import generate_narrative_outline, select_segments_for_narrative
from app.config import AppConfig

logger = logging.getLogger(__name__)


class VideoProcessingService:
    """Service for processing videos in the new project-based workflow."""
    
    def __init__(self, db):
        self.db = db
    
    async def process_video_for_edit(
        self,
        project_id: str,
        source_video_id: str,
        edit_name: str,
        user_prompt: str = "",
        editing_settings: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[callable] = None
    ) -> str:
        """
        Process a video to create a new edit with EDL.
        
        Args:
            project_id: ID of the project
            source_video_id: ID of the source video
            edit_name: Name for the new edit
            user_prompt: User's prompt for AI analysis
            editing_settings: Dictionary of editing settings
            progress_callback: Optional callback for progress updates
        
        Returns:
            edit_id: ID of the created edit
        """
        
        def update_progress(stage: str, message: str, percent: float = 0):
            """Helper to update progress."""
            if progress_callback:
                progress_callback(stage, message, percent)
            logger.info(f"[{stage}] {message} ({percent}%)")
        
        try:
            # Get source video
            source_video = SourceVideoDAO.get_by_id(self.db, source_video_id)
            if not source_video or source_video.project_id != project_id:
                raise ValueError(f"Source video {source_video_id} not found in project {project_id}")
            
            update_progress("init", "Starting video processing", 0)
            
            # Create the edit record
            edit = EditDAO.create(
                db=self.db,
                project_id=project_id,
                source_video_id=source_video_id,
                name=edit_name,
                user_prompt=user_prompt,
                editing_settings=editing_settings or {}
            )
            
            update_progress("edit_created", f"Created edit: {edit.name}", 5)
            
            # Check if transcript already exists
            segments = TranscriptSegmentDAO.get_by_video(self.db, source_video_id)
            
            if not segments:
                # Need to transcribe
                update_progress("transcription", "Transcribing video...", 10)
                
                # Get settings from editing_settings or use defaults
                settings = editing_settings or {}
                whisper_model = settings.get('whisper_model', 'medium')
                language = settings.get('language', 'en')
                audio_track = settings.get('audio_track', 0)
                
                # Transcribe the video
                transcript_result = await asyncio.to_thread(
                    transcribe_video,
                    source_video.file_path,
                    model_name=whisper_model,
                    language=language,
                    audio_track=audio_track
                )
                
                # Save transcript segments to database
                segments_data = transcript_result.get('segments', [])
                segments = TranscriptSegmentDAO.create_many(
                    db=self.db,
                    source_video_id=source_video_id,
                    segments=segments_data
                )
                
                update_progress("transcription", f"Transcribed {len(segments)} segments", 40)
            else:
                update_progress("transcription", f"Using existing transcript with {len(segments)} segments", 40)
            
            # AI Analysis: Generate narrative outline
            if user_prompt:
                update_progress("ai_analysis", "Generating narrative outline with AI...", 50)
                
                # Prepare segments for Gemini
                segments_for_ai = [
                    {
                        'start': seg.start_time,
                        'end': seg.end_time,
                        'text': seg.text
                    }
                    for seg in segments
                ]
                
                # Generate narrative outline
                narrative_outline = await asyncio.to_thread(
                    generate_narrative_outline,
                    segments_for_ai,
                    user_prompt
                )
                
                # Save narrative outline to edit
                EditDAO.update(
                    db=self.db,
                    edit_id=edit.id,
                    narrative_outline=narrative_outline
                )
                
                update_progress("ai_analysis", "Narrative outline generated", 60)
                
                # AI Analysis: Select segments
                update_progress("ai_selection", "AI selecting segments...", 65)
                
                # Select segments for narrative (simplified for now)
                selected_segments = await asyncio.to_thread(
                    select_segments_for_narrative,
                    segments_for_ai,
                    narrative_outline,
                    user_prompt,
                    ""  # past_text_context
                )
                
                update_progress("ai_selection", f"AI selected {len(selected_segments)} segments", 80)
            else:
                # No AI prompt - include all segments
                selected_segments = [
                    {'start': seg.start_time}
                    for seg in segments
                ]
                narrative_outline = []
                update_progress("selection", f"Including all {len(segments)} segments", 80)
            
            # Create Edit Decision List (EDL)
            update_progress("edl_creation", "Creating Edit Decision List...", 85)
            
            # Build EDL from selected segments
            segment_map = {seg.start_time: seg for seg in segments}
            
            decisions_data = []
            for idx, selected in enumerate(selected_segments):
                start_time = selected['start']
                segment = segment_map.get(start_time)
                
                if segment:
                    # Apply padding if specified
                    pad_before = editing_settings.get('pad_before_seconds', 0.0) if editing_settings else 0.0
                    pad_after = editing_settings.get('pad_after_seconds', 0.0) if editing_settings else 0.0
                    
                    decisions_data.append({
                        'segment_id': segment.id,
                        'source_video_id': source_video_id,
                        'order_index': idx,
                        'start_time': max(0, segment.start_time - pad_before),
                        'end_time': segment.end_time + pad_after,
                        'transcript_text': segment.text,
                        'is_ai_selected': bool(user_prompt),
                        'is_included': True
                    })
            
            # Save EDL to database
            if decisions_data:
                EditDecisionDAO.create_many(self.db, edit.id, decisions_data)
            
            update_progress("edl_creation", f"Created EDL with {len(decisions_data)} clips", 95)
            
            # Mark AI processing as complete
            EditDAO.update(
                db=self.db,
                edit_id=edit.id,
                ai_processing_complete=True
            )
            
            update_progress("complete", "Processing complete!", 100)
            
            return edit.id
            
        except Exception as e:
            logger.error(f"Error processing video: {e}", exc_info=True)
            update_progress("error", f"Error: {str(e)}", 0)
            raise
    
    async def add_segments_to_edit(
        self,
        edit_id: str,
        segment_ids: List[str],
        insert_at: Optional[int] = None
    ) -> List[str]:
        """
        Add segments to an existing edit's EDL.
        
        Args:
            edit_id: ID of the edit
            segment_ids: List of transcript segment IDs to add
            insert_at: Optional position to insert at (default: append to end)
        
        Returns:
            List of created decision IDs
        """
        # Get the edit
        edit = EditDAO.get_with_decisions(self.db, edit_id)
        if not edit:
            raise ValueError(f"Edit {edit_id} not found")
        
        # Get current max order index
        if insert_at is None:
            insert_at = len(edit.edit_decisions)
        
        # Create decisions for new segments
        decisions_data = []
        for i, segment_id in enumerate(segment_ids):
            segment = TranscriptSegmentDAO.get_by_id(self.db, segment_id)
            if not segment:
                logger.warning(f"Segment {segment_id} not found, skipping")
                continue
            
            decisions_data.append({
                'segment_id': segment.id,
                'source_video_id': segment.source_video_id,
                'order_index': insert_at + i,
                'start_time': segment.start_time,
                'end_time': segment.end_time,
                'transcript_text': segment.text,
                'is_ai_selected': False,
                'is_included': True,
                'user_modified': True
            })
        
        # Shift existing decisions if inserting in the middle
        if insert_at < len(edit.edit_decisions):
            for decision in edit.edit_decisions[insert_at:]:
                EditDecisionDAO.update(
                    self.db,
                    decision.id,
                    order_index=decision.order_index + len(decisions_data)
                )
        
        # Create new decisions
        new_decisions = EditDecisionDAO.create_many(self.db, edit_id, decisions_data)
        
        return [d.id for d in new_decisions]
    
    def get_edit_preview_data(self, edit_id: str) -> Dict[str, Any]:
        """
        Get data needed for previewing an edit.
        
        Returns:
            Dictionary with clips list and metadata
        """
        edit = EditDAO.get_with_decisions(self.db, edit_id)
        if not edit:
            raise ValueError(f"Edit {edit_id} not found")
        
        # Get only included decisions, in order
        included_decisions = [d for d in edit.edit_decisions if d.is_included]
        included_decisions.sort(key=lambda x: x.order_index)
        
        clips = []
        total_duration = 0.0
        
        for decision in included_decisions:
            duration = decision.end_time - decision.start_time
            total_duration += duration
            
            clips.append({
                'decision_id': decision.id,
                'order_index': decision.order_index,
                'start_time': decision.start_time,
                'end_time': decision.end_time,
                'duration': duration,
                'transcript_text': decision.transcript_text,
                'source_video_id': decision.source_video_id,
                'clip_file_path': decision.clip_file_path
            })
        
        return {
            'edit_id': edit.id,
            'edit_name': edit.name,
            'clips': clips,
            'total_duration': total_duration,
            'clip_count': len(clips),
            'source_video_id': edit.source_video_id
        }

