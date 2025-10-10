"""
SQLAlchemy models for GeminiEditor.
Defines the database schema for projects, source videos, transcripts, edits, and edit decisions.
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import json
from typing import Optional, List, Dict, Any
from datetime import datetime


class Project(Base):
    """
    Project model - container for all related videos and edits.
    """
    __tablename__ = "projects"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    settings = Column(Text, nullable=True)  # JSON string of ProjectSettings

    # Relationships
    source_videos = relationship("SourceVideo", back_populates="project", cascade="all, delete-orphan")
    edits = relationship("Edit", back_populates="project", cascade="all, delete-orphan")

    def get_settings(self) -> Dict[str, Any]:
        """Parse settings JSON."""
        if self.settings:
            return json.loads(self.settings)
        return {}

    def set_settings(self, settings: Dict[str, Any]):
        """Set settings as JSON."""
        self.settings = json.dumps(settings)
    
    @property
    def settings_dict(self) -> Dict[str, Any]:
        """Get settings as a dictionary for API responses."""
        return self.get_settings()


class SourceVideo(Base):
    """
    Source video model - represents uploaded video files.
    """
    __tablename__ = "source_videos"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)
    duration = Column(Float, nullable=True)
    uploaded_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Media info
    video_codec = Column(String, nullable=True)
    audio_tracks = Column(Text, nullable=True)  # JSON array of AudioTrack
    resolution = Column(Text, nullable=True)  # JSON object {width, height}
    framerate = Column(Float, nullable=True)
    
    # Processing artifacts
    transcript_path = Column(String, nullable=True)
    audio_preview_paths = Column(Text, nullable=True)  # JSON array of paths
    
    # Optional scope (pre-trim)
    scope_start = Column(Float, nullable=True)
    scope_end = Column(Float, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="source_videos")
    transcript_segments = relationship("TranscriptSegment", back_populates="source_video", cascade="all, delete-orphan")
    edits = relationship("Edit", back_populates="source_video")
    edit_decisions = relationship("EditDecision", back_populates="source_video")

    def get_audio_tracks(self) -> List[Dict[str, Any]]:
        """Parse audio tracks JSON."""
        if self.audio_tracks:
            return json.loads(self.audio_tracks)
        return []

    def set_audio_tracks(self, tracks: List[Dict[str, Any]]):
        """Set audio tracks as JSON."""
        self.audio_tracks = json.dumps(tracks)

    def get_resolution(self) -> Optional[Dict[str, int]]:
        """Parse resolution JSON."""
        if self.resolution:
            return json.loads(self.resolution)
        return None

    def set_resolution(self, width: int, height: int):
        """Set resolution as JSON."""
        self.resolution = json.dumps({"width": width, "height": height})

    def get_audio_preview_paths(self) -> List[str]:
        """Parse audio preview paths JSON."""
        if self.audio_preview_paths:
            return json.loads(self.audio_preview_paths)
        return []

    def set_audio_preview_paths(self, paths: List[str]):
        """Set audio preview paths as JSON."""
        self.audio_preview_paths = json.dumps(paths)


class TranscriptSegment(Base):
    """
    Transcript segment model - represents a timestamped segment of transcribed text.
    """
    __tablename__ = "transcript_segments"

    id = Column(String, primary_key=True)
    source_video_id = Column(String, ForeignKey("source_videos.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    words = Column(Text, nullable=True)  # JSON array of Word objects with word-level timing
    confidence = Column(Float, nullable=True)
    speaker = Column(String, nullable=True)  # Future: speaker diarization

    # Relationships
    source_video = relationship("SourceVideo", back_populates="transcript_segments")
    edit_decisions = relationship("EditDecision", back_populates="segment")

    # Indexes for performance
    __table_args__ = (
        Index('idx_transcript_segments_video', 'source_video_id'),
        Index('idx_transcript_segments_time', 'source_video_id', 'start_time', 'end_time'),
    )

    def get_words(self) -> List[Dict[str, Any]]:
        """Parse words JSON."""
        if self.words:
            return json.loads(self.words)
        return []

    def set_words(self, words: List[Dict[str, Any]]):
        """Set words as JSON."""
        self.words = json.dumps(words)
    
    @property
    def words_list(self) -> List[Dict[str, Any]]:
        """Get words as a list for API responses."""
        return self.get_words()


class Edit(Base):
    """
    Edit model - represents a version of an edited video with its edit decision list.
    """
    __tablename__ = "edits"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Source reference
    source_video_id = Column(String, ForeignKey("source_videos.id"), nullable=False)
    
    # AI-generated artifacts
    narrative_outline = Column(Text, nullable=True)  # JSON array of strings
    user_prompt = Column(Text, nullable=True)
    
    # Processing metadata
    ai_processing_complete = Column(Boolean, default=False, nullable=False)
    multimodal_pass_complete = Column(Boolean, default=False, nullable=False)
    
    # Export status
    is_finalized = Column(Boolean, default=False, nullable=False)
    final_video_path = Column(String, nullable=True)
    finalized_at = Column(DateTime, nullable=True)
    
    # Settings used for this edit
    editing_settings = Column(Text, nullable=True)  # JSON object of EditingSettings

    # Relationships
    project = relationship("Project", back_populates="edits")
    source_video = relationship("SourceVideo", back_populates="edits")
    edit_decisions = relationship("EditDecision", back_populates="edit", cascade="all, delete-orphan", order_by="EditDecision.order_index")

    def get_narrative_outline(self) -> List[str]:
        """Parse narrative outline JSON."""
        if self.narrative_outline:
            return json.loads(self.narrative_outline)
        return []

    def set_narrative_outline(self, outline: List[str]):
        """Set narrative outline as JSON."""
        self.narrative_outline = json.dumps(outline)

    def get_editing_settings(self) -> Dict[str, Any]:
        """Parse editing settings JSON."""
        if self.editing_settings:
            return json.loads(self.editing_settings)
        return {}

    def set_editing_settings(self, settings: Dict[str, Any]):
        """Set editing settings as JSON."""
        self.editing_settings = json.dumps(settings)


class EditDecision(Base):
    """
    Edit decision model - represents a single clip in the edit decision list (EDL).
    """
    __tablename__ = "edit_decisions"

    id = Column(String, primary_key=True)
    edit_id = Column(String, ForeignKey("edits.id", ondelete="CASCADE"), nullable=False)
    order_index = Column(Integer, nullable=False)
    
    # Clip definition
    segment_id = Column(String, ForeignKey("transcript_segments.id"), nullable=False)
    source_video_id = Column(String, ForeignKey("source_videos.id"), nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    
    # Clip metadata (denormalized for easy display)
    transcript_text = Column(Text, nullable=False)
    
    # Editing state
    is_included = Column(Boolean, default=True, nullable=False)
    is_ai_selected = Column(Boolean, default=False, nullable=False)
    user_modified = Column(Boolean, default=False, nullable=False)
    
    # Visual/preview artifacts
    clip_file_path = Column(String, nullable=True)
    thumbnail_path = Column(String, nullable=True)

    # Relationships
    edit = relationship("Edit", back_populates="edit_decisions")
    segment = relationship("TranscriptSegment", back_populates="edit_decisions")
    source_video = relationship("SourceVideo", back_populates="edit_decisions")

    # Index for performance
    __table_args__ = (
        Index('idx_edit_decisions_edit', 'edit_id', 'order_index'),
    )

