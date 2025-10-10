"""
API routes for Source Videos.
Handles operations related to uploaded videos.
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import shutil
import uuid
from pathlib import Path

from app.database import get_db
from app.dao import SourceVideoDAO, TranscriptSegmentDAO
from app.schemas import (
    SourceVideoResponse,
    TranscriptSegmentResponse,
    SourceVideoUpdate
)

router = APIRouter(prefix="/api/projects/{project_id}/source-videos", tags=["source-videos"])


@router.get("/", response_model=List[SourceVideoResponse])
def list_source_videos(project_id: str, db: Session = Depends(get_db)):
    """List all source videos for a project."""
    videos = SourceVideoDAO.get_by_project(db, project_id)
    return videos


@router.post("/upload", response_model=SourceVideoResponse, status_code=status.HTTP_201_CREATED)
async def upload_source_video(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload a new source video to a project."""
    # Validate file type
    if not file.content_type or not file.content_type.startswith('video/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a video"
        )
    
    # Validate file size (max 15GB)
    file_size = 0
    content = await file.read()
    file_size = len(content)
    if file_size > 15 * 1024 * 1024 * 1024:  # 15GB
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size must be less than 15GB"
        )
    
    # Create uploads directory if it doesn't exist
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(exist_ok=True)
    
    # Generate unique filename
    file_extension = Path(file.filename).suffix if file.filename else '.mp4'
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = uploads_dir / unique_filename
    
    # Save file
    try:
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        # Create source video record
        video = SourceVideoDAO.create(
            db=db,
            project_id=project_id,
            filename=file.filename or unique_filename,
            file_path=str(file_path),
            file_size=file_size
        )
        
        return video
        
    except Exception as e:
        # Clean up file if database operation fails
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload video: {str(e)}"
        )


@router.get("/{video_id}", response_model=SourceVideoResponse)
def get_source_video(project_id: str, video_id: str, db: Session = Depends(get_db)):
    """Get a specific source video."""
    video = SourceVideoDAO.get_by_id(db, video_id)
    if not video or video.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source video with ID {video_id} not found in project {project_id}"
        )
    return video


@router.get("/{video_id}/transcript", response_model=List[TranscriptSegmentResponse])
def get_video_transcript(project_id: str, video_id: str, db: Session = Depends(get_db)):
    """Get the transcript segments for a source video."""
    video = SourceVideoDAO.get_by_id(db, video_id)
    if not video or video.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source video with ID {video_id} not found"
        )
    
    segments = TranscriptSegmentDAO.get_by_video(db, video_id)
    return segments


@router.get("/{video_id}/play")
def stream_video(project_id: str, video_id: str, request: Request, db: Session = Depends(get_db)):
    """Stream a source video file using the modular video streaming service."""
    # Get video from database
    video = SourceVideoDAO.get_by_id(db, video_id)
    if not video or video.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source video with ID {video_id} not found"
        )
    
    # Use the modular video streaming service
    from app.services.video_streaming import stream_video_file
    return stream_video_file(video.file_path, video.filename, request)


@router.patch("/{video_id}", response_model=SourceVideoResponse)
def update_source_video(
    project_id: str,
    video_id: str,
    video_update: SourceVideoUpdate,
    db: Session = Depends(get_db)
):
    """Update a source video's metadata."""
    video = SourceVideoDAO.get_by_id(db, video_id)
    if not video or video.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source video with ID {video_id} not found"
        )
    
    updated_video = SourceVideoDAO.update(
        db=db,
        video_id=video_id,
        **video_update.model_dump(exclude_unset=True)
    )
    
    return updated_video


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source_video(project_id: str, video_id: str, db: Session = Depends(get_db)):
    """
    Delete a source video and all associated data.
    WARNING: This will delete the transcript and any edits based on this video.
    """
    video = SourceVideoDAO.get_by_id(db, video_id)
    if not video or video.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source video with ID {video_id} not found"
        )
    
    success = SourceVideoDAO.delete(db, video_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete source video"
        )
    return None

