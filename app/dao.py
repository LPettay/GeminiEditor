"""
Data Access Object (DAO) layer for GeminiEditor.
Provides CRUD operations for all database models.
"""

from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from app.models import Project, SourceVideo, TranscriptSegment, Edit, EditDecision
from app.database import get_db


# ==================== PROJECT DAO ====================

class ProjectDAO:
    """Data access operations for Project model."""
    
    @staticmethod
    def create(db: Session, name: str, description: Optional[str] = None, 
               settings: Optional[Dict[str, Any]] = None) -> Project:
        """Create a new project."""
        project = Project(
            id=str(uuid.uuid4()),
            name=name,
            description=description
        )
        # Always set settings - use empty dict if None provided
        project.set_settings(settings or {})
        
        db.add(project)
        db.commit()
        db.refresh(project)
        return project
    
    @staticmethod
    def get_by_id(db: Session, project_id: str) -> Optional[Project]:
        """Get a project by ID."""
        return db.query(Project).filter(Project.id == project_id).first()
    
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[Project]:
        """Get all projects with pagination."""
        return db.query(Project).order_by(Project.updated_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def update(db: Session, project_id: str, name: Optional[str] = None, 
               description: Optional[str] = None, settings: Optional[Dict[str, Any]] = None) -> Optional[Project]:
        """Update a project."""
        project = ProjectDAO.get_by_id(db, project_id)
        if not project:
            return None
        
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        if settings is not None:
            project.set_settings(settings)
        
        project.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(project)
        return project
    
    @staticmethod
    def delete(db: Session, project_id: str) -> bool:
        """Delete a project and all its related data."""
        project = ProjectDAO.get_by_id(db, project_id)
        if not project:
            return False
        
        db.delete(project)
        db.commit()
        return True
    
    @staticmethod
    def get_with_videos(db: Session, project_id: str) -> Optional[Project]:
        """Get a project with its source videos eagerly loaded."""
        return db.query(Project).options(
            joinedload(Project.source_videos)
        ).filter(Project.id == project_id).first()
    
    @staticmethod
    def get_with_edits(db: Session, project_id: str) -> Optional[Project]:
        """Get a project with its edits eagerly loaded."""
        return db.query(Project).options(
            joinedload(Project.edits)
        ).filter(Project.id == project_id).first()


# ==================== SOURCE VIDEO DAO ====================

class SourceVideoDAO:
    """Data access operations for SourceVideo model."""
    
    @staticmethod
    def create(db: Session, project_id: str, filename: str, file_path: str,
               file_size: Optional[int] = None, duration: Optional[float] = None,
               video_codec: Optional[str] = None, framerate: Optional[float] = None,
               scope_start: Optional[float] = None, scope_end: Optional[float] = None) -> SourceVideo:
        """Create a new source video."""
        video = SourceVideo(
            id=str(uuid.uuid4()),
            project_id=project_id,
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            duration=duration,
            video_codec=video_codec,
            framerate=framerate,
            scope_start=scope_start,
            scope_end=scope_end
        )
        
        db.add(video)
        db.commit()
        db.refresh(video)
        return video
    
    @staticmethod
    def get_by_id(db: Session, video_id: str) -> Optional[SourceVideo]:
        """Get a source video by ID."""
        return db.query(SourceVideo).filter(SourceVideo.id == video_id).first()
    
    @staticmethod
    def get_by_project(db: Session, project_id: str) -> List[SourceVideo]:
        """Get all source videos for a project."""
        return db.query(SourceVideo).filter(
            SourceVideo.project_id == project_id
        ).order_by(SourceVideo.uploaded_at.desc()).all()
    
    @staticmethod
    def update(db: Session, video_id: str, **kwargs) -> Optional[SourceVideo]:
        """Update a source video with arbitrary fields."""
        video = SourceVideoDAO.get_by_id(db, video_id)
        if not video:
            return None
        
        # Update allowed fields
        allowed_fields = [
            'filename', 'file_size', 'duration', 'video_codec', 'framerate',
            'transcript_path', 'scope_start', 'scope_end'
        ]
        
        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                setattr(video, key, value)
        
        # Handle JSON fields separately
        if 'audio_tracks' in kwargs and kwargs['audio_tracks'] is not None:
            video.set_audio_tracks(kwargs['audio_tracks'])
        if 'resolution' in kwargs and kwargs['resolution'] is not None:
            video.set_resolution(kwargs['resolution']['width'], kwargs['resolution']['height'])
        if 'audio_preview_paths' in kwargs and kwargs['audio_preview_paths'] is not None:
            video.set_audio_preview_paths(kwargs['audio_preview_paths'])
        
        db.commit()
        db.refresh(video)
        return video
    
    @staticmethod
    def delete(db: Session, video_id: str) -> bool:
        """Delete a source video and all related data."""
        video = SourceVideoDAO.get_by_id(db, video_id)
        if not video:
            return False
        
        db.delete(video)
        db.commit()
        return True
    
    @staticmethod
    def get_with_segments(db: Session, video_id: str) -> Optional[SourceVideo]:
        """Get a source video with transcript segments eagerly loaded."""
        return db.query(SourceVideo).options(
            joinedload(SourceVideo.transcript_segments)
        ).filter(SourceVideo.id == video_id).first()


# ==================== TRANSCRIPT SEGMENT DAO ====================

class TranscriptSegmentDAO:
    """Data access operations for TranscriptSegment model."""
    
    @staticmethod
    def create(db: Session, source_video_id: str, start_time: float, end_time: float,
               text: str, words: Optional[List[Dict[str, Any]]] = None,
               confidence: Optional[float] = None, speaker: Optional[str] = None) -> TranscriptSegment:
        """Create a new transcript segment."""
        segment = TranscriptSegment(
            id=str(uuid.uuid4()),
            source_video_id=source_video_id,
            start_time=start_time,
            end_time=end_time,
            text=text,
            confidence=confidence,
            speaker=speaker
        )
        
        if words:
            segment.set_words(words)
        
        db.add(segment)
        db.commit()
        db.refresh(segment)
        return segment
    
    @staticmethod
    def create_many(db: Session, source_video_id: str, segments: List[Dict[str, Any]]) -> List[TranscriptSegment]:
        """Create multiple transcript segments at once (bulk insert)."""
        segment_objects = []
        for seg in segments:
            segment = TranscriptSegment(
                id=str(uuid.uuid4()),
                source_video_id=source_video_id,
                start_time=seg['start'],
                end_time=seg['end'],
                text=seg['text'],
                confidence=seg.get('confidence'),
                speaker=seg.get('speaker')
            )
            
            if 'words' in seg and seg['words']:
                segment.set_words(seg['words'])
            
            segment_objects.append(segment)
        
        db.add_all(segment_objects)
        db.commit()
        return segment_objects
    
    @staticmethod
    def get_by_id(db: Session, segment_id: str) -> Optional[TranscriptSegment]:
        """Get a transcript segment by ID."""
        return db.query(TranscriptSegment).filter(TranscriptSegment.id == segment_id).first()
    
    @staticmethod
    def get_by_video(db: Session, source_video_id: str) -> List[TranscriptSegment]:
        """Get all transcript segments for a source video."""
        return db.query(TranscriptSegment).filter(
            TranscriptSegment.source_video_id == source_video_id
        ).order_by(TranscriptSegment.start_time).all()
    
    @staticmethod
    def get_by_time_range(db: Session, source_video_id: str, 
                          start_time: float, end_time: float) -> List[TranscriptSegment]:
        """Get transcript segments within a time range."""
        return db.query(TranscriptSegment).filter(
            TranscriptSegment.source_video_id == source_video_id,
            TranscriptSegment.start_time >= start_time,
            TranscriptSegment.end_time <= end_time
        ).order_by(TranscriptSegment.start_time).all()
    
    @staticmethod
    def delete_by_video(db: Session, source_video_id: str) -> int:
        """Delete all transcript segments for a video. Returns count deleted."""
        count = db.query(TranscriptSegment).filter(
            TranscriptSegment.source_video_id == source_video_id
        ).delete()
        db.commit()
        return count


# ==================== EDIT DAO ====================

class EditDAO:
    """Data access operations for Edit model."""
    
    @staticmethod
    def create(db: Session, project_id: str, source_video_id: str, name: str,
               user_prompt: Optional[str] = None, narrative_outline: Optional[List[str]] = None,
               editing_settings: Optional[Dict[str, Any]] = None) -> Edit:
        """Create a new edit."""
        # Get the next version number for this project
        existing_edits = db.query(Edit).filter(Edit.project_id == project_id).all()
        version = len(existing_edits) + 1
        
        edit = Edit(
            id=str(uuid.uuid4()),
            project_id=project_id,
            source_video_id=source_video_id,
            name=name,
            version=version,
            user_prompt=user_prompt
        )
        
        if narrative_outline:
            edit.set_narrative_outline(narrative_outline)
        if editing_settings:
            edit.set_editing_settings(editing_settings)
        
        db.add(edit)
        db.commit()
        db.refresh(edit)
        return edit
    
    @staticmethod
    def get_by_id(db: Session, edit_id: str) -> Optional[Edit]:
        """Get an edit by ID."""
        return db.query(Edit).filter(Edit.id == edit_id).first()
    
    @staticmethod
    def get_by_project(db: Session, project_id: str) -> List[Edit]:
        """Get all edits for a project."""
        return db.query(Edit).filter(
            Edit.project_id == project_id
        ).order_by(Edit.version.desc()).all()
    
    @staticmethod
    def update(db: Session, edit_id: str, name: Optional[str] = None,
               ai_processing_complete: Optional[bool] = None,
               multimodal_pass_complete: Optional[bool] = None,
               is_finalized: Optional[bool] = None,
               final_video_path: Optional[str] = None,
               narrative_outline: Optional[List[str]] = None,
               editing_settings: Optional[Dict[str, Any]] = None) -> Optional[Edit]:
        """Update an edit."""
        edit = EditDAO.get_by_id(db, edit_id)
        if not edit:
            return None
        
        if name is not None:
            edit.name = name
        if ai_processing_complete is not None:
            edit.ai_processing_complete = ai_processing_complete
        if multimodal_pass_complete is not None:
            edit.multimodal_pass_complete = multimodal_pass_complete
        if is_finalized is not None:
            edit.is_finalized = is_finalized
            if is_finalized:
                edit.finalized_at = datetime.utcnow()
        if final_video_path is not None:
            edit.final_video_path = final_video_path
        if narrative_outline is not None:
            edit.set_narrative_outline(narrative_outline)
        if editing_settings is not None:
            edit.set_editing_settings(editing_settings)
        
        edit.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(edit)
        return edit
    
    @staticmethod
    def delete(db: Session, edit_id: str) -> bool:
        """Delete an edit and all its edit decisions."""
        edit = EditDAO.get_by_id(db, edit_id)
        if not edit:
            return False
        
        db.delete(edit)
        db.commit()
        return True
    
    @staticmethod
    def get_with_decisions(db: Session, edit_id: str) -> Optional[Edit]:
        """Get an edit with its edit decisions eagerly loaded."""
        return db.query(Edit).options(
            joinedload(Edit.edit_decisions)
        ).filter(Edit.id == edit_id).first()
    
    @staticmethod
    def duplicate(db: Session, edit_id: str, new_name: Optional[str] = None) -> Optional[Edit]:
        """Duplicate an edit with all its edit decisions."""
        original = EditDAO.get_with_decisions(db, edit_id)
        if not original:
            return None
        
        # Create new edit
        new_edit = Edit(
            id=str(uuid.uuid4()),
            project_id=original.project_id,
            source_video_id=original.source_video_id,
            name=new_name or f"{original.name} (Copy)",
            version=original.version + 1,
            user_prompt=original.user_prompt,
            narrative_outline=original.narrative_outline,
            editing_settings=original.editing_settings,
            ai_processing_complete=original.ai_processing_complete,
            multimodal_pass_complete=original.multimodal_pass_complete
        )
        
        db.add(new_edit)
        db.flush()  # Get the new edit ID
        
        # Duplicate all edit decisions
        for decision in original.edit_decisions:
            new_decision = EditDecision(
                id=str(uuid.uuid4()),
                edit_id=new_edit.id,
                order_index=decision.order_index,
                segment_id=decision.segment_id,
                source_video_id=decision.source_video_id,
                start_time=decision.start_time,
                end_time=decision.end_time,
                transcript_text=decision.transcript_text,
                is_included=decision.is_included,
                is_ai_selected=decision.is_ai_selected,
                user_modified=decision.user_modified,
                clip_file_path=decision.clip_file_path,
                thumbnail_path=decision.thumbnail_path
            )
            db.add(new_decision)
        
        db.commit()
        db.refresh(new_edit)
        return new_edit


# ==================== EDIT DECISION DAO ====================

class EditDecisionDAO:
    """Data access operations for EditDecision model."""
    
    @staticmethod
    def create(db: Session, edit_id: str, segment_id: str, source_video_id: str,
               order_index: int, start_time: float, end_time: float, transcript_text: str,
               is_ai_selected: bool = False, is_included: bool = True) -> EditDecision:
        """Create a new edit decision."""
        decision = EditDecision(
            id=str(uuid.uuid4()),
            edit_id=edit_id,
            segment_id=segment_id,
            source_video_id=source_video_id,
            order_index=order_index,
            start_time=start_time,
            end_time=end_time,
            transcript_text=transcript_text,
            is_ai_selected=is_ai_selected,
            is_included=is_included
        )
        
        db.add(decision)
        db.commit()
        db.refresh(decision)
        return decision
    
    @staticmethod
    def create_many(db: Session, edit_id: str, decisions: List[Dict[str, Any]]) -> List[EditDecision]:
        """Create multiple edit decisions at once (bulk insert)."""
        decision_objects = []
        for idx, dec in enumerate(decisions):
            decision = EditDecision(
                id=str(uuid.uuid4()),
                edit_id=edit_id,
                segment_id=dec['segment_id'],
                source_video_id=dec['source_video_id'],
                order_index=dec.get('order_index', idx),
                start_time=dec['start_time'],
                end_time=dec['end_time'],
                transcript_text=dec['transcript_text'],
                is_ai_selected=dec.get('is_ai_selected', False),
                is_included=dec.get('is_included', True),
                user_modified=dec.get('user_modified', False),
                clip_file_path=dec.get('clip_file_path'),
                thumbnail_path=dec.get('thumbnail_path')
            )
            decision_objects.append(decision)
        
        db.add_all(decision_objects)
        db.commit()
        return decision_objects
    
    @staticmethod
    def get_by_id(db: Session, decision_id: str) -> Optional[EditDecision]:
        """Get an edit decision by ID."""
        return db.query(EditDecision).filter(EditDecision.id == decision_id).first()
    
    @staticmethod
    def get_by_edit(db: Session, edit_id: str, included_only: bool = False) -> List[EditDecision]:
        """Get all edit decisions for an edit, ordered by order_index."""
        query = db.query(EditDecision).filter(EditDecision.edit_id == edit_id)
        
        if included_only:
            query = query.filter(EditDecision.is_included == True)
        
        return query.order_by(EditDecision.order_index).all()
    
    @staticmethod
    def update(db: Session, decision_id: str, **kwargs) -> Optional[EditDecision]:
        """Update an edit decision with arbitrary fields."""
        decision = EditDecisionDAO.get_by_id(db, decision_id)
        if not decision:
            return None
        
        # Update allowed fields
        allowed_fields = [
            'order_index', 'start_time', 'end_time', 'transcript_text',
            'is_included', 'user_modified', 'clip_file_path', 'thumbnail_path'
        ]
        
        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                setattr(decision, key, value)
        
        # Mark as user modified if certain fields changed
        if any(k in kwargs for k in ['order_index', 'start_time', 'end_time', 'is_included']):
            decision.user_modified = True
        
        db.commit()
        db.refresh(decision)
        return decision
    
    @staticmethod
    def reorder(db: Session, edit_id: str, decision_order: List[str]) -> bool:
        """Reorder edit decisions based on a list of decision IDs."""
        decisions = EditDecisionDAO.get_by_edit(db, edit_id)
        decision_map = {d.id: d for d in decisions}
        
        for new_index, decision_id in enumerate(decision_order):
            if decision_id in decision_map:
                decision_map[decision_id].order_index = new_index
                decision_map[decision_id].user_modified = True
        
        db.commit()
        return True
    
    @staticmethod
    def delete(db: Session, decision_id: str) -> bool:
        """Delete an edit decision."""
        decision = EditDecisionDAO.get_by_id(db, decision_id)
        if not decision:
            return False
        
        db.delete(decision)
        db.commit()
        return True
    
    @staticmethod
    def delete_by_edit(db: Session, edit_id: str) -> int:
        """Delete all edit decisions for an edit. Returns count deleted."""
        count = db.query(EditDecision).filter(
            EditDecision.edit_id == edit_id
        ).delete()
        db.commit()
        return count

