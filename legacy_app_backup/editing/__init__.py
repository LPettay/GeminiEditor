"""
Editing Strategies Package

This package contains different strategies for processing video transcript segments
to achieve various editing styles.
"""

from .base import EditingStrategy
from .chronological import ChronologicalEditingStrategy
from .custom import CustomEditingStrategy

__all__ = [
    "EditingStrategy",
    "ChronologicalEditingStrategy",
    "CustomEditingStrategy"
] 