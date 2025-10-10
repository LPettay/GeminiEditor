"""
Pydantic schemas for API request/response validation.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== PROJECT SCHEMAS ====================

class ProjectCreate(BaseModel):
    """Schema for creating a new project."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class ProjectResponse(BaseModel):
    """Schema for project API responses."""
    id: str
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    settings: Optional[Dict[str, Any]] = Field(default=None, alias='settings_dict')
    
    class Config:
        from_attributes = True
        populate_by_name = True


class ProjectWithVideosResponse(ProjectResponse):
    """Project response with source videos included."""
    source_videos: List['SourceVideoResponse']


class ProjectWithEditsResponse(ProjectResponse):
    """Project response with edits included."""
    edits: List['EditResponse']


# ==================== SOURCE VIDEO SCHEMAS ====================

class AudioTrack(BaseModel):
    """Schema for audio track metadata."""
    index: int
    codec: str
    sample_rate: int
    channels: int
    language: Optional[str] = None


class Resolution(BaseModel):
    """Schema for video resolution."""
    width: int
    height: int


class SourceVideoCreate(BaseModel):
    """Schema for creating a source video record."""
    project_id: str
    filename: str
    file_path: str
    file_size: Optional[int] = None
    duration: Optional[float] = None
    video_codec: Optional[str] = None
    framerate: Optional[float] = None
    scope_start: Optional[float] = None
    scope_end: Optional[float] = None


class SourceVideoUpdate(BaseModel):
    """Schema for updating a source video."""
    filename: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[float] = None
    video_codec: Optional[str] = None
    audio_tracks: Optional[List[AudioTrack]] = None
    resolution: Optional[Resolution] = None
    framerate: Optional[float] = None
    transcript_path: Optional[str] = None
    audio_preview_paths: Optional[List[str]] = None
    scope_start: Optional[float] = None
    scope_end: Optional[float] = None


class SourceVideoResponse(BaseModel):
    """Schema for source video API responses."""
    id: str
    project_id: str
    filename: str
    file_path: str
    file_size: Optional[int]
    duration: Optional[float]
    uploaded_at: datetime
    video_codec: Optional[str]
    audio_tracks: Optional[List[AudioTrack]] = None
    resolution: Optional[Resolution] = None
    framerate: Optional[float] = None
    transcript_path: Optional[str] = None
    audio_preview_paths: Optional[List[str]] = None
    scope_start: Optional[float]
    scope_end: Optional[float]
    
    class Config:
        from_attributes = True


# ==================== TRANSCRIPT SEGMENT SCHEMAS ====================

class Word(BaseModel):
    """Schema for word-level timing."""
    word: str
    start: float
    end: float
    confidence: float


class TranscriptSegmentCreate(BaseModel):
    """Schema for creating a transcript segment."""
    source_video_id: str
    start_time: float = Field(..., alias='start')
    end_time: float = Field(..., alias='end')
    text: str
    words: Optional[List[Word]] = None
    confidence: Optional[float] = None
    speaker: Optional[str] = None
    
    class Config:
        populate_by_name = True


class TranscriptSegmentResponse(BaseModel):
    """Schema for transcript segment API responses."""
    id: str
    source_video_id: str
    start_time: float = Field(alias='start')
    end_time: float = Field(alias='end')
    text: str
    words: Optional[List[Word]] = Field(default=None, alias='words_list')
    confidence: Optional[float]
    speaker: Optional[str]
    
    class Config:
        from_attributes = True
        populate_by_name = True


# ==================== EDIT SCHEMAS ====================

class EditCreate(BaseModel):
    """Schema for creating a new edit."""
    project_id: str
    source_video_id: str
    name: str = Field(..., min_length=1, max_length=255)
    user_prompt: Optional[str] = None
    narrative_outline: Optional[List[str]] = None
    editing_settings: Optional[Dict[str, Any]] = None


class EditUpdate(BaseModel):
    """Schema for updating an edit."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    ai_processing_complete: Optional[bool] = None
    multimodal_pass_complete: Optional[bool] = None
    is_finalized: Optional[bool] = None
    final_video_path: Optional[str] = None
    narrative_outline: Optional[List[str]] = None
    editing_settings: Optional[Dict[str, Any]] = None


class EditResponse(BaseModel):
    """Schema for edit API responses."""
    id: str
    project_id: str
    name: str
    version: int
    created_at: datetime
    updated_at: datetime
    source_video_id: str
    narrative_outline: Optional[List[str]]
    user_prompt: Optional[str]
    ai_processing_complete: bool
    multimodal_pass_complete: bool
    is_finalized: bool
    final_video_path: Optional[str]
    finalized_at: Optional[datetime]
    editing_settings: Dict[str, Any]
    
    class Config:
        from_attributes = True


class EditWithDecisionsResponse(EditResponse):
    """Edit response with edit decisions included."""
    edit_decisions: List['EditDecisionResponse']


# ==================== EDIT DECISION SCHEMAS ====================

class EditDecisionCreate(BaseModel):
    """Schema for creating an edit decision."""
    edit_id: str
    segment_id: str
    source_video_id: str
    order_index: int
    start_time: float
    end_time: float
    transcript_text: str
    is_ai_selected: bool = False
    is_included: bool = True


class EditDecisionUpdate(BaseModel):
    """Schema for updating an edit decision."""
    order_index: Optional[int] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    transcript_text: Optional[str] = None
    is_included: Optional[bool] = None
    user_modified: Optional[bool] = None
    clip_file_path: Optional[str] = None
    thumbnail_path: Optional[str] = None


class EditDecisionResponse(BaseModel):
    """Schema for edit decision API responses."""
    id: str
    edit_id: str
    order_index: int
    segment_id: str
    source_video_id: str
    start_time: float
    end_time: float
    transcript_text: str
    is_included: bool
    is_ai_selected: bool
    user_modified: bool
    clip_file_path: Optional[str]
    thumbnail_path: Optional[str]
    
    class Config:
        from_attributes = True


class EDLReorderRequest(BaseModel):
    """Schema for reordering edit decisions."""
    decision_order: List[str] = Field(..., description="Ordered list of decision IDs")


# ==================== FINALIZATION SCHEMAS ====================

class FinalizeRequest(BaseModel):
    """Schema for finalizing an edit."""
    output_name: Optional[str] = None
    resolution: Optional[str] = "1920x1080"
    codec: Optional[str] = "libx264"
    bitrate: Optional[str] = "5M"


class FinalizeResponse(BaseModel):
    """Schema for finalization response."""
    job_id: str
    status: str
    message: str


# ==================== PREVIEW SCHEMAS ====================

class ClipPreview(BaseModel):
    """Schema for a single clip in the preview."""
    decision_id: str
    clip_url: str
    start_time: float
    end_time: float
    duration: float
    transcript_text: str
    order_index: int


class PreviewResponse(BaseModel):
    """Schema for edit preview response."""
    edit_id: str
    clips: List[ClipPreview]
    total_duration: float
    clip_count: int


# Update forward references
ProjectWithVideosResponse.model_rebuild()
ProjectWithEditsResponse.model_rebuild()
EditWithDecisionsResponse.model_rebuild()

