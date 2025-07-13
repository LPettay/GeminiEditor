"""
Configuration module for video processing application.
Defines feature flags, editing styles, and processing settings using Pydantic models.
"""

from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Optional, Any
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class EditingStyle(str, Enum):
    """Defines the fundamental approach to segment arrangement."""
    CHRONOLOGICAL = "chronological"  # Segments are kept in their original order, no repetitions.
    CUSTOM = "custom"                # Segment arrangement is controlled by feature flags.

class EditingFeatureFlags(BaseModel):
    """Flags to control specific editing behaviors, primarily for CUSTOM style."""
    allow_reordering: bool = Field(False, description="Allow reordering of segments/phrases. For CUSTOM style, this enables full creative reordering by Gemini Pass 3. For CHRONOLOGICAL, this is ignored (reordering is never allowed).")
    allow_repetition: bool = Field(False, description="Allow repetition of segments. For CUSTOM style, if phrase editing is not active, this enables segment-level repetition. If phrase editing IS active, Gemini Pass 3 controls phrase repetition. For CHRONOLOGICAL, if phrase editing is active, Gemini Pass 3 controls phrase repetition; otherwise, no repetition.")
    max_segment_repetitions: int = Field(1, ge=1, description="Max times a segment can be repeated (if segment-level repetition is active).")
    enable_phrase_level_editing: bool = Field(False, description="Enable advanced editing features: secondary word-level transcription and Gemini Pass 3 for phrase scripting. If False, editing strategies operate on segment-level transcriptions only.")

class AudioProcessingConfig(BaseModel):
    """Configuration for audio processing and silence detection."""
    silence_threshold: float = Field(
        default=-50.0,
        le=0.0,
        description="Silence detection threshold in dB"
    )
    min_silence_duration: float = Field(
        default=0.2,
        ge=0.0,
        description="Minimum silence duration in seconds"
    )
    audio_enhancement: bool = Field(
        default=True,
        description="Apply audio enhancement during processing"
    )

class TranscriptionConfig(BaseModel):
    """Configuration for video transcription."""
    model_name: str = Field(
        default="base",
        description="Whisper model name to use for transcription"
    )
    language: str = Field(
        default="en",
        description="Language code for transcription"
    )
    save_speech_audio: bool = Field(
        default=False,
        description="Save speech-only audio file"
    )

class GeminiConfig(BaseModel):
    """Configuration for Gemini AI processing."""
    chunk_size: int = Field(
        default=250,
        ge=1,
        description="Size of transcript chunks for Gemini processing"
    )
    api_key: str = Field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", ""),
        description="Gemini API key from environment"
    )

class AppConfig(BaseModel):
    """Main application configuration model, bundling all settings."""
    editing_style: EditingStyle
    feature_flags: EditingFeatureFlags
    transcription_config: TranscriptionConfig
    audio_config: AudioProcessingConfig
    gemini_config: GeminiConfig

    @field_validator('editing_style', mode='before')
    @classmethod
    def ensure_editing_style_is_enum(cls, v: Any) -> EditingStyle:
        # ---- START DEBUG PRINT ----
        print(f"[VALIDATOR DEBUG] ensure_editing_style_is_enum called with value: {v}, type: {type(v)}", flush=True)
        # ---- END DEBUG PRINT ----
        if isinstance(v, EditingStyle):
            print("[VALIDATOR DEBUG] Value is already EditingStyle enum.", flush=True)
            return v
        if isinstance(v, str):
            print(f"[VALIDATOR DEBUG] Value is string '{v}', attempting conversion.", flush=True)
            try:
                enum_member = EditingStyle(v.lower())
                print(f"[VALIDATOR DEBUG] Converted to enum member: {enum_member}, type: {type(enum_member)}", flush=True)
                return enum_member # Convert string to enum member, be case-insensitive for input
            except ValueError as e:
                print(f"[VALIDATOR DEBUG] ValueError during conversion: {e}", flush=True)
                raise ValueError(f"Invalid editing style string: '{v}'. Must be one of {[item.value for item in EditingStyle]}.")
        print(f"[VALIDATOR DEBUG] Value is neither EditingStyle nor string. Type: {type(v)}", flush=True)
        raise TypeError(f"Invalid type for editing_style: {type(v)}. Must be EditingStyle enum or valid string.")

    # Potentially add methods here for easy access or validation logic
    # e.g., def should_run_pass_3(self) -> bool:
    #     return self.feature_flags.enable_phrase_level_editing

    class Config:
        # use_enum_values = True # Ensure enum values are used when serializing --- Test commenting this out
        validate_assignment = True # Good for ensuring type safety on later assignments 