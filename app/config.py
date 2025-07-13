"""
Configuration module for video processing application.
Defines feature flags, editing styles, and processing settings using Pydantic models.
"""

from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

class EditingFeatureFlags(BaseModel):
    """Flags to control specific editing behaviors."""
    enable_phrase_level_editing: bool = Field(
        default=False, 
        description="Enable advanced editing features: secondary word-level transcription and (future) Gemini Pass 3 for phrase scripting."
    )
    allow_reordering: bool = Field(
        default=False, 
        description="Allow reordering of segments/phrases. This is the primary flag to enable non-chronological video assembly."
    )
    allow_repetition: bool = Field(
        default=False, 
        description="Allow repetition of segments/phrases. Specific behavior may depend on other flags like enable_phrase_level_editing."
    )
    max_segment_repetitions: int = Field(
        default=1, 
        ge=1, 
        description="Max times a segment can be repeated (if segment-level repetition is active/applicable)."
    )

class TranscriptionConfig(BaseModel):
    """Configuration for the transcription process."""
    model_name: str = Field(default="medium", description="Whisper model name (e.g., tiny, base, small, medium, large).")
    language: str = Field(default="en", description="Language code for transcription (e.g., en, es, fr).")
    save_speech_audio: bool = Field(default=False, description="Save a separate speech-only audio file during initial transcription.")

class AudioProcessingConfig(BaseModel):
    """Configuration for audio processing, e.g., silence detection."""
    silence_threshold: float = Field(default=-50.0, le=0.0, description="Silence threshold in dB for VAD (e.g., -50.0). Must be <= 0.")
    min_silence_duration: float = Field(default=0.2, ge=0.0, description="Minimum silence duration in seconds for VAD.")
    # audio_enhancement: bool = Field(default=True, description="Apply audio enhancement during processing - Placeholder")

class GeminiConfig(BaseModel):
    """Configuration for Gemini API calls."""
    api_key: str = Field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", ""), 
        description="Gemini API key. Loaded from GEMINI_API_KEY environment variable."
    )
    chunk_size: int = Field(
        default=250, 
        ge=1, 
        description="Number of segments per chunk for Gemini Pass 2 processing (if applicable)."
    )
    reuse_latest_augmented_segments: bool = Field(
        default=False,
        description="If phrase-level editing is enabled, attempt to reuse the most recent existing augmented segment file for this video, skipping word-level transcription."
    )
    # model_name_pass1: str = "models/gemini-1.5-flash-latest" # Example
    # model_name_pass2: str = "models/gemini-1.5-pro-latest" # Example
    # model_name_pass3: str = "models/gemini-1.5-pro-latest" # Example

class AppConfig(BaseModel):
    """Main application configuration model, bundling all settings."""
    # editing_style: EditingStyle field is fully removed.
    feature_flags: EditingFeatureFlags = Field(default_factory=EditingFeatureFlags)
    transcription_config: TranscriptionConfig = Field(default_factory=TranscriptionConfig)
    audio_config: AudioProcessingConfig = Field(default_factory=AudioProcessingConfig)
    gemini_config: GeminiConfig = Field(default_factory=GeminiConfig)

    class Config:
        validate_assignment = True # Good for ensuring type safety on later assignments 