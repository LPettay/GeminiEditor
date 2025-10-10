"""
API module initialization.
"""

from .projects import router as projects_router
from .source_videos import router as source_videos_router
from .edits import router as edits_router
from .processing import router as processing_router

__all__ = ['projects_router', 'source_videos_router', 'edits_router', 'processing_router']

