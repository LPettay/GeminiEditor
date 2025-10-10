"""
API routes for Edits.
Handles operations related to edit versions and edit decision lists.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, FileResponse
from typing import List
import os
from pathlib import Path
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.dao import EditDAO, EditDecisionDAO
from app.schemas import (
    EditCreate,
    EditUpdate,
    EditResponse,
    EditWithDecisionsResponse,
    EditDecisionResponse,
    EditDecisionUpdate,
    EDLReorderRequest
)
from app.services.hls_service import build_playlist_content, ensure_cmaf_for_decision
from app.dao import EditDecisionDAO, SourceVideoDAO

router = APIRouter(prefix="/api/projects/{project_id}/edits", tags=["edits"])


@router.post("/", response_model=EditResponse, status_code=status.HTTP_201_CREATED)
def create_edit(project_id: str, edit: EditCreate, db: Session = Depends(get_db)):
    """Create a new edit."""
    if edit.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project ID in URL must match project ID in request body"
        )
    
    new_edit = EditDAO.create(
        db=db,
        project_id=edit.project_id,
        source_video_id=edit.source_video_id,
        name=edit.name,
        user_prompt=edit.user_prompt,
        narrative_outline=edit.narrative_outline,
        editing_settings=edit.editing_settings
    )
    return new_edit


@router.get("/", response_model=List[EditResponse])
def list_edits(project_id: str, db: Session = Depends(get_db)):
    """List all edits for a project."""
    edits = EditDAO.get_by_project(db, project_id)
    return edits


@router.get("/{edit_id}", response_model=EditResponse)
def get_edit(project_id: str, edit_id: str, db: Session = Depends(get_db)):
    """Get a specific edit."""
    edit = EditDAO.get_by_id(db, edit_id)
    if not edit or edit.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edit with ID {edit_id} not found in project {project_id}"
        )
    return edit


@router.get("/{edit_id}/with-decisions", response_model=EditWithDecisionsResponse)
def get_edit_with_decisions(project_id: str, edit_id: str, db: Session = Depends(get_db)):
    """Get an edit with all its edit decisions (EDL)."""
    edit = EditDAO.get_with_decisions(db, edit_id)
    if not edit or edit.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edit with ID {edit_id} not found"
        )
    return edit


@router.patch("/{edit_id}", response_model=EditResponse)
def update_edit(
    project_id: str,
    edit_id: str,
    edit_update: EditUpdate,
    db: Session = Depends(get_db)
):
    """Update an edit."""
    edit = EditDAO.get_by_id(db, edit_id)
    if not edit or edit.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edit with ID {edit_id} not found"
        )
    
    updated_edit = EditDAO.update(
        db=db,
        edit_id=edit_id,
        **edit_update.model_dump(exclude_unset=True)
    )
    
    return updated_edit


@router.post("/{edit_id}/duplicate", response_model=EditResponse, status_code=status.HTTP_201_CREATED)
def duplicate_edit(
    project_id: str,
    edit_id: str,
    new_name: str = None,
    db: Session = Depends(get_db)
):
    """Duplicate an edit with all its edit decisions."""
    edit = EditDAO.get_by_id(db, edit_id)
    if not edit or edit.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edit with ID {edit_id} not found"
        )
    
    duplicated_edit = EditDAO.duplicate(db, edit_id, new_name)
    if not duplicated_edit:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to duplicate edit"
        )
    
    return duplicated_edit


@router.delete("/{edit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_edit(project_id: str, edit_id: str, db: Session = Depends(get_db)):
    """Delete an edit and all its edit decisions."""
    edit = EditDAO.get_by_id(db, edit_id)
    if not edit or edit.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edit with ID {edit_id} not found"
        )
    
    success = EditDAO.delete(db, edit_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete edit"
        )
    return None


# ==================== HLS PREVIEW (VOD) ====================

@router.get("/{edit_id}/playlist.m3u8")
def get_hls_playlist(project_id: str, edit_id: str, db: Session = Depends(get_db)):
    """
    Generate an HLS VOD playlist for the edit's current EDL order.
    Each entry maps to a single fMP4 segment built from the source video.
    """
    edit = EditDAO.get_with_decisions(db, edit_id)
    if not edit or edit.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Edit not found")

    # Get included decisions in order
    decisions = [d for d in edit.edit_decisions if d.is_included]
    decisions.sort(key=lambda d: d.order_index)

    # Ensure CMAF exists for each decision (idempotent)
    source_video = SourceVideoDAO.get_by_id(db, edit.source_video_id)
    if not source_video:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Source video not found")

    items = []
    for d in decisions:
        # Build/init on demand for newly created videos
        ensure_cmaf_for_decision(
            edit_id=edit_id,
            decision_id=d.id,
            source_video_path=source_video.file_path,
            start_time=float(d.start_time),
            end_time=float(d.end_time),
        )
        items.append((d.id, float(max(0.01, d.end_time - d.start_time))))

    playlist = build_playlist_content(project_id, edit_id, items)
    return Response(content=playlist, media_type="application/vnd.apple.mpegurl")


@router.get("/{edit_id}/segments/{segment_name}")
def get_hls_segment(project_id: str, edit_id: str, segment_name: str):
    """
    Serve init (.init.mp4) or media (.m4s) file for a decision.
    """
    base_dir = Path("tmp") / "hls" / edit_id / "segments"
    file_path = base_dir / segment_name
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")

    # Set appropriate MIME based on extension
    if segment_name.endswith(".init") or segment_name.endswith(".init.mp4"):
        media_type = "video/mp4"
    elif segment_name.endswith(".m4s"):
        media_type = "video/iso.segment"
    else:
        media_type = "application/octet-stream"

    # CORS/cache headers suitable for segments
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD",
        "Access-Control-Allow-Headers": "Range",
    }

    return FileResponse(str(file_path), media_type=media_type, headers=headers)


# ==================== EDIT DECISION ROUTES ====================

@router.get("/{edit_id}/edl", response_model=List[EditDecisionResponse])
def get_edit_decision_list(
    project_id: str,
    edit_id: str,
    included_only: bool = False,
    db: Session = Depends(get_db)
):
    """Get the edit decision list (EDL) for an edit."""
    edit = EditDAO.get_by_id(db, edit_id)
    if not edit or edit.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edit with ID {edit_id} not found"
        )
    
    decisions = EditDecisionDAO.get_by_edit(db, edit_id, included_only=included_only)
    return decisions


@router.patch("/{edit_id}/edl/{decision_id}", response_model=EditDecisionResponse)
def update_edit_decision(
    project_id: str,
    edit_id: str,
    decision_id: str,
    decision_update: EditDecisionUpdate,
    db: Session = Depends(get_db)
):
    """Update a specific edit decision."""
    decision = EditDecisionDAO.get_by_id(db, decision_id)
    if not decision or decision.edit_id != edit_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edit decision with ID {decision_id} not found"
        )
    
    updated_decision = EditDecisionDAO.update(
        db=db,
        decision_id=decision_id,
        **decision_update.model_dump(exclude_unset=True)
    )
    
    return updated_decision


@router.post("/{edit_id}/edl/reorder", response_model=List[EditDecisionResponse])
def reorder_edit_decisions(
    project_id: str,
    edit_id: str,
    reorder_request: EDLReorderRequest,
    db: Session = Depends(get_db)
):
    """Reorder edit decisions in the EDL."""
    edit = EditDAO.get_by_id(db, edit_id)
    if not edit or edit.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edit with ID {edit_id} not found"
        )
    
    success = EditDecisionDAO.reorder(db, edit_id, reorder_request.decision_order)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reorder edit decisions"
        )
    
    # Return the reordered list
    decisions = EditDecisionDAO.get_by_edit(db, edit_id)
    return decisions


@router.delete("/{edit_id}/edl/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_edit_decision(
    project_id: str,
    edit_id: str,
    decision_id: str,
    db: Session = Depends(get_db)
):
    """Delete an edit decision from the EDL."""
    decision = EditDecisionDAO.get_by_id(db, decision_id)
    if not decision or decision.edit_id != edit_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edit decision with ID {decision_id} not found"
        )
    
    success = EditDecisionDAO.delete(db, decision_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete edit decision"
        )
    return None

