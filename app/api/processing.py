"""
API routes for video processing, preview, and finalization.
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from sqlalchemy.orm import Session
from typing import Optional
import asyncio
import uuid
import os
import logging

from app.database import get_db
from app.dao import EditDAO, SourceVideoDAO
from app.services import VideoProcessingService
from app.services.video_processing_service import process_video_for_editing, ProcessingResult
from app.services.video_segmentation import VideoSegmentationService, SegmentationResult
from app.schemas import FinalizeRequest, FinalizeResponse, PreviewResponse, ClipPreview, TranscriptSegmentResponse
from app.ffmpeg_utils import cut_and_concatenate

logger = logging.getLogger(__name__)
router = APIRouter(tags=["processing"])

# Store for tracking background jobs
processing_jobs = {}

# Store for transcript processing jobs
transcript_jobs = {}

# Store for video segmentation jobs
segmentation_jobs = {}


@router.post("/api/projects/{project_id}/source-videos/{video_id}/process")
async def process_video(
    project_id: str,
    video_id: str,
    edit_name: str,
    user_prompt: str = "",
    whisper_model: str = "medium",
    language: str = "en",
    audio_track: int = 0,
    pad_before_seconds: float = 0.5,
    pad_after_seconds: float = 0.5,
    db: Session = Depends(get_db)
):
    """
    Process a source video to create a new edit with AI-selected segments.
    This creates an EDL (Edit Decision List) without actually concatenating the video.
    """
    
    # Verify source video exists in project
    source_video = SourceVideoDAO.get_by_id(db, video_id)
    if not source_video or source_video.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source video {video_id} not found in project {project_id}"
        )
    
    # Create job ID for tracking
    job_id = str(uuid.uuid4())
    processing_jobs[job_id] = {
        'status': 'processing',
        'progress': 0,
        'message': 'Starting processing...',
        'edit_id': None
    }
    
    # Define progress callback
    def progress_callback(stage: str, message: str, percent: float):
        processing_jobs[job_id]['progress'] = percent
        processing_jobs[job_id]['message'] = message
    
    try:
        # Create service
        service = VideoProcessingService(db)
        
        # Prepare editing settings
        editing_settings = {
            'whisper_model': whisper_model,
            'language': language,
            'audio_track': audio_track,
            'pad_before_seconds': pad_before_seconds,
            'pad_after_seconds': pad_after_seconds
        }
        
        # Process the video
        edit_id = await service.process_video_for_edit(
            project_id=project_id,
            source_video_id=video_id,
            edit_name=edit_name,
            user_prompt=user_prompt,
            editing_settings=editing_settings,
            progress_callback=progress_callback
        )
        
        # Update job status
        processing_jobs[job_id]['status'] = 'completed'
        processing_jobs[job_id]['edit_id'] = edit_id
        processing_jobs[job_id]['progress'] = 100
        processing_jobs[job_id]['message'] = 'Processing complete!'
        
        return {
            'job_id': job_id,
            'edit_id': edit_id,
            'status': 'completed',
            'message': 'Video processed successfully. Edit ready for preview.'
        }
        
    except Exception as e:
        processing_jobs[job_id]['status'] = 'failed'
        processing_jobs[job_id]['message'] = str(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}"
        )


@router.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of a processing job."""
    if job_id not in processing_jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    
    return processing_jobs[job_id]


@router.get("/api/projects/{project_id}/edits/{edit_id}/preview", response_model=PreviewResponse)
async def get_edit_preview(
    project_id: str,
    edit_id: str,
    db: Session = Depends(get_db)
):
    """
    Get preview data for an edit.
    Returns the list of clips with URLs for sequential playback.
    """
    
    # Verify edit exists in project
    edit = EditDAO.get_by_id(db, edit_id)
    if not edit or edit.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edit {edit_id} not found in project {project_id}"
        )
    
    # Get preview data
    service = VideoProcessingService(db)
    preview_data = service.get_edit_preview_data(edit_id)
    
    # Get source video for base URL
    source_video = SourceVideoDAO.get_by_id(db, preview_data['source_video_id'])
    if not source_video:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Source video not found"
        )
    
    # Build clip preview objects with URLs
    clips = []
    for clip_data in preview_data['clips']:
        # For now, we'll use the source video URL with time parameters
        # Later we can extract individual clips
        clip_url = f"/api/source-videos/{source_video.id}/stream?start={clip_data['start_time']}&end={clip_data['end_time']}"
        
        clips.append(ClipPreview(
            decision_id=clip_data['decision_id'],
            clip_url=clip_url,
            start_time=clip_data['start_time'],
            end_time=clip_data['end_time'],
            duration=clip_data['duration'],
            transcript_text=clip_data['transcript_text'],
            order_index=clip_data['order_index']
        ))
    
    return PreviewResponse(
        edit_id=edit_id,
        clips=clips,
        total_duration=preview_data['total_duration'],
        clip_count=preview_data['clip_count']
    )


@router.post("/api/projects/{project_id}/edits/{edit_id}/finalize", response_model=FinalizeResponse)
async def finalize_edit(
    project_id: str,
    edit_id: str,
    finalize_request: FinalizeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Finalize an edit by actually concatenating the clips into a single video file.
    This is the final export step.
    """
    
    # Verify edit exists and is not already finalized
    edit = EditDAO.get_with_decisions(db, edit_id)
    if not edit or edit.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edit {edit_id} not found in project {project_id}"
        )
    
    if edit.is_finalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Edit is already finalized"
        )
    
    # Get source video
    source_video = SourceVideoDAO.get_by_id(db, edit.source_video_id)
    if not source_video:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Source video not found"
        )
    
    # Create job ID
    job_id = str(uuid.uuid4())
    processing_jobs[job_id] = {
        'status': 'finalizing',
        'progress': 0,
        'message': 'Starting finalization...',
        'edit_id': edit_id
    }
    
    # Define finalization task
    async def finalize_task():
        try:
            processing_jobs[job_id]['message'] = 'Preparing segments...'
            processing_jobs[job_id]['progress'] = 10
            
            # Get included decisions in order
            included_decisions = [d for d in edit.edit_decisions if d.is_included]
            included_decisions.sort(key=lambda x: x.order_index)
            
            if not included_decisions:
                processing_jobs[job_id]['status'] = 'failed'
                processing_jobs[job_id]['message'] = 'No clips to concatenate'
                return
            
            # Build segments list for cut_and_concatenate
            segments = [
                {'start': d.start_time, 'end': d.end_time}
                for d in included_decisions
            ]
            
            processing_jobs[job_id]['message'] = f'Concatenating {len(segments)} clips...'
            processing_jobs[job_id]['progress'] = 30
            
            # Generate output filename
            output_name = finalize_request.output_name or f"{edit.name}_final"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{output_name}_{timestamp}.mp4"
            output_path = os.path.join("processed", output_filename)
            
            # Ensure processed directory exists
            os.makedirs("processed", exist_ok=True)
            
            # Run concatenation
            await asyncio.to_thread(
                cut_and_concatenate,
                source_video.file_path,
                segments,
                output_path,
                audio_track=0  # TODO: Get from settings
            )
            
            processing_jobs[job_id]['message'] = 'Updating database...'
            processing_jobs[job_id]['progress'] = 90
            
            # Update edit record
            EditDAO.update(
                db=db,
                edit_id=edit_id,
                is_finalized=True,
                final_video_path=output_path
            )
            
            processing_jobs[job_id]['status'] = 'completed'
            processing_jobs[job_id]['progress'] = 100
            processing_jobs[job_id]['message'] = 'Finalization complete!'
            processing_jobs[job_id]['output_path'] = output_path
            
        except Exception as e:
            processing_jobs[job_id]['status'] = 'failed'
            processing_jobs[job_id]['message'] = str(e)
    
    # Start background task
    background_tasks.add_task(finalize_task)
    
    return FinalizeResponse(
        job_id=job_id,
        status='finalizing',
        message='Finalization started. Check job status for progress.'
    )


@router.post("/api/projects/{project_id}/source-videos/{video_id}/generate-transcript")
async def generate_transcript_for_editing(
    project_id: str,
    video_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Generate transcript and prepare video for text-based editing.
    This creates the foundation for rearrangeable clips.
    """
    # Get video from database
    video = SourceVideoDAO.get_by_id(db, video_id)
    if not video or video.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source video with ID {video_id} not found"
        )
    
    # Check if file exists
    if not os.path.exists(video.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found on disk"
        )
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    
    # Initialize job status
    transcript_jobs[job_id] = {
        "status": "processing",
        "progress": 0,
        "message": "Starting transcript generation...",
        "video_id": video_id,
        "project_id": project_id,
    }
    
    # Start background processing
    background_tasks.add_task(
        _process_video_transcript,
        job_id,
        video_id,
        video.file_path,
        project_id,
        db
    )
    
    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Transcript generation started"
    }


async def _process_video_transcript(job_id: str, video_id: str, video_path: str, project_id: str, db: Session):
    """Background task to process video transcript."""
    try:
        def progress_callback(progress: int, message: str):
            if job_id in transcript_jobs:
                transcript_jobs[job_id]["progress"] = progress
                transcript_jobs[job_id]["message"] = message
        
        # Process video for editing
        result: ProcessingResult = await process_video_for_editing(
            video_id,
            video_path,
            progress_callback
        )
        
        if result.success:
            # Save transcript segments to database
            from app.dao import TranscriptSegmentDAO
            
            # Clear existing segments
            TranscriptSegmentDAO.delete_by_video(db, video_id)
            
            # Save new segments
            for segment in result.transcript_segments:
                TranscriptSegmentDAO.create(
                    db=db,
                    source_video_id=video_id,
                    start_time=segment.start,
                    end_time=segment.end,
                    text=segment.text,
                    confidence=segment.confidence,
                    speaker=segment.speaker,
                    words=[{
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                        "confidence": word.confidence
                    } for word in segment.words]
                )
            
            # Update job status
            transcript_jobs[job_id] = {
                "status": "completed",
                "progress": 100,
                "message": "Transcript generation completed successfully",
                "video_id": video_id,
                "project_id": project_id,  # Use the project_id from the endpoint
                "segment_count": len(result.transcript_segments),
                "duration": result.video_metadata.get("duration", 0),
            }
        else:
            transcript_jobs[job_id] = {
                "status": "failed",
                "progress": 0,
                "message": f"Transcript generation failed: {result.error_message}",
                "video_id": video_id,
                "error": result.error_message,
            }
    
    except Exception as e:
        transcript_jobs[job_id] = {
            "status": "failed",
            "progress": 0,
            "message": f"Transcript generation failed: {str(e)}",
            "video_id": video_id,
            "error": str(e),
        }


@router.get("/api/projects/{project_id}/source-videos/{video_id}/transcript-status/{job_id}")
async def get_transcript_status(
    project_id: str,
    video_id: str,
    job_id: str,
    db: Session = Depends(get_db)
):
    """Get the status of transcript generation job."""
    if job_id not in transcript_jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    job_data = transcript_jobs[job_id]
    
    # Verify job belongs to this video
    if job_data.get("video_id") != video_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job does not belong to this video"
        )
    
    return job_data


@router.get("/api/projects/{project_id}/edits/{edit_id}/download")
async def download_finalized_edit(
    project_id: str,
    edit_id: str,
    db: Session = Depends(get_db)
):
    """
    Download the finalized video file.
    """
    from fastapi.responses import FileResponse
    
    edit = EditDAO.get_by_id(db, edit_id)
    if not edit or edit.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edit {edit_id} not found"
        )
    
    if not edit.is_finalized or not edit.final_video_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Edit is not finalized yet"
        )
    
    if not os.path.exists(edit.final_video_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Finalized video file not found"
        )
    
    return FileResponse(
        edit.final_video_path,
        media_type="video/mp4",
        filename=os.path.basename(edit.final_video_path)
    )


@router.get("/api/source-videos/{video_id}/stream")
async def stream_source_video_segment(
    video_id: str,
    start: Optional[float] = None,
    end: Optional[float] = None,
    db: Session = Depends(get_db)
):
    """
    Stream a segment of a source video.
    Supports range requests for video player compatibility.
    """
    from fastapi.responses import FileResponse
    
    video = SourceVideoDAO.get_by_id(db, video_id)
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video {video_id} not found"
        )
    
    if not os.path.exists(video.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found"
        )
    
    # For now, just return the full video file
    # TODO: Implement actual segment extraction or time-based range requests
    return FileResponse(
        video.file_path,
        media_type="video/mp4",
        filename=os.path.basename(video.file_path)
    )


@router.post("/api/projects/{project_id}/source-videos/{video_id}/segment")
async def segment_video_for_editing(
    project_id: str,
    video_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Segment a video into clips based on transcript segments for text-based editing.
    """
    # Get video from database
    video = SourceVideoDAO.get_by_id(db, video_id)
    if not video:
        # Let's see what videos are actually in the database for this project
        project_videos = SourceVideoDAO.get_by_project(db, project_id)
        logger.error(f"Video with ID {video_id} not found in database")
        logger.error(f"Available videos in project {project_id}: {[(v.id, v.filename, v.file_path) for v in project_videos]}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source video with ID {video_id} not found in database"
        )
    
    if video.project_id != project_id:
        logger.error(f"Video {video_id} belongs to project {video.project_id}, not {project_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source video with ID {video_id} not found in project {project_id}"
        )
    
    logger.info(f"Found video: {video.filename} at {video.file_path}")
    
    # Check if file exists
    if not os.path.exists(video.file_path):
        logger.error(f"Video file not found on disk: {video.file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video file not found on disk: {video.file_path}"
        )
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    
    # Initialize job status
    segmentation_jobs[job_id] = {
        "status": "processing",
        "progress": 0,
        "message": "Starting video segmentation...",
        "video_id": video_id,
        "project_id": project_id,
    }
    
    # Start background processing
    background_tasks.add_task(
        _segment_video_background,
        job_id,
        video_id,
        video.file_path,
        project_id
    )
    
    return {
        "job_id": job_id,
        "status": "processing",
        "message": "Video segmentation started"
    }


async def _segment_video_background(job_id: str, video_id: str, video_path: str, project_id: str):
    """Background task to segment video into clips."""
    logger.info(f"Starting background segmentation task for job {job_id}, video {video_id}")
    try:
        def progress_callback(progress: int, message: str):
            logger.info(f"Progress callback for {job_id}: {progress}% - {message}")
            if job_id in segmentation_jobs:
                segmentation_jobs[job_id]["progress"] = progress
                segmentation_jobs[job_id]["message"] = message
                logger.info(f"Updated job progress: {segmentation_jobs[job_id]}")
        
        # Segment video for editing
        from app.services.video_segmentation import video_segmentation_service
        result: SegmentationResult = await video_segmentation_service.segment_video_for_editing(
            video_id,
            video_path,
            progress_callback
        )
        
        if result.success:
            logger.info(f"Segmentation completed successfully with {len(result.clips)} clips")
            # Update job status with success
            segmentation_jobs[job_id] = {
                "status": "completed",
                "progress": 100,
                "message": "Video segmentation completed successfully",
                "video_id": video_id,
                "project_id": project_id,
                "clip_count": len(result.clips),
                "clips": [
                    {
                        "id": clip.id,
                        "segment_id": clip.segment_id,
                        "start_time": clip.start_time,
                        "end_time": clip.end_time,
                        "duration": clip.duration,
                        "order_index": clip.order_index,
                        "stream_url": f"/api/projects/{project_id}/clips/{clip.id}/play"  # Simplified URL generation
                    }
                    for clip in result.clips
                ]
            }
            logger.info(f"Updated job status for {job_id}: {segmentation_jobs[job_id]['status']}")
        else:
            logger.error(f"Segmentation failed: {result.error_message}")
            segmentation_jobs[job_id] = {
                "status": "failed",
                "progress": 0,
                "message": f"Video segmentation failed: {result.error_message}",
                "video_id": video_id,
                "error": result.error_message,
            }
    
    except Exception as e:
        segmentation_jobs[job_id] = {
            "status": "failed",
            "progress": 0,
            "message": f"Video segmentation failed: {str(e)}",
            "video_id": video_id,
            "error": str(e),
        }


@router.get("/api/projects/{project_id}/source-videos/{video_id}/segmentation-status/{job_id}")
async def get_segmentation_status(
    project_id: str,
    video_id: str,
    job_id: str
):
    """Get the status of video segmentation job."""
    if job_id not in segmentation_jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    job_data = segmentation_jobs[job_id]
    
    # Verify job belongs to this video
    if job_data.get("video_id") != video_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job does not belong to this video"
        )
    
    return job_data


@router.get("/api/projects/{project_id}/clips/{clip_id}/play")
def stream_clip(project_id: str, clip_id: str, request: Request):
    """Stream a video clip file."""
    from app.services.video_streaming import stream_video_file
    
    # For now, we need to find the clip file path
    # TODO: Implement proper clip storage and retrieval
    # This is a placeholder - in a real implementation, you'd store clip metadata in the database
    
    # For now, return an error
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Clip streaming not yet implemented"
    )

