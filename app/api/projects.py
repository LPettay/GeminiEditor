"""
API routes for Projects.
Handles CRUD operations for projects.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.dao import ProjectDAO
from app.schemas import (
    ProjectCreate, 
    ProjectUpdate, 
    ProjectResponse,
    ProjectWithVideosResponse,
    ProjectWithEditsResponse
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(project: ProjectCreate, db: Session = Depends(get_db)):
    """Create a new project."""
    new_project = ProjectDAO.create(
        db=db,
        name=project.name,
        description=project.description,
        settings=project.settings
    )
    return new_project


@router.get("/", response_model=List[ProjectResponse])
def list_projects(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all projects with pagination."""
    projects = ProjectDAO.get_all(db, skip=skip, limit=limit)
    return projects


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    """Get a specific project by ID."""
    project = ProjectDAO.get_by_id(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )
    return project


@router.get("/{project_id}/with-videos", response_model=ProjectWithVideosResponse)
def get_project_with_videos(project_id: str, db: Session = Depends(get_db)):
    """Get a project with its source videos included."""
    project = ProjectDAO.get_with_videos(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )
    return project


@router.get("/{project_id}/with-edits", response_model=ProjectWithEditsResponse)
def get_project_with_edits(project_id: str, db: Session = Depends(get_db)):
    """Get a project with its edits included."""
    project = ProjectDAO.get_with_edits(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )
    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str, 
    project_update: ProjectUpdate, 
    db: Session = Depends(get_db)
):
    """Update a project."""
    updated_project = ProjectDAO.update(
        db=db,
        project_id=project_id,
        name=project_update.name,
        description=project_update.description,
        settings=project_update.settings
    )
    
    if not updated_project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )
    
    return updated_project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    """
    Delete a project and all associated data.
    WARNING: This will delete all source videos, transcripts, edits, and edit decisions.
    """
    success = ProjectDAO.delete(db, project_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )
    return None

