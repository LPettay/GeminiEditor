"""
API routes for Edits.
Handles operations related to edit versions and edit decision lists.
"""

from fastapi import APIRouter, Depends, HTTPException, status
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

