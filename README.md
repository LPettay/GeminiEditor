# VoiceoverV2 Project

## Overview

VoiceoverV2 is a Python-based application designed to process video files. It automates the transcription of audio from videos, allows for AI-powered refinement of the transcript to select key segments, and then generates a new video file based on these segments. The primary goal is to create concise, edited videos from longer recordings by intelligently removing silences and optionally applying further content selection criteria via a generative AI model.

The application is built using FastAPI, providing a web API for interaction.

## Core Functionality

1.  **File Upload**: Users can upload video files via an API endpoint.
2.  **Audio Transcription**: The audio from the uploaded video is transcribed using OpenAI Whisper. This process includes:
    *   Extracting the audio track from the video.
    *   Detecting silences in the audio to identify speech segments.
    *   Transcribing the identified speech segments.
    *   Optionally saving a concatenated audio file containing only the speech segments.
3.  **Transcript Processing (Optional)**: The generated transcript can be processed by Google's Gemini Pro model. Users can provide a prompt to guide the AI in selecting or filtering transcript segments based on specific criteria (e.g., relevance, conciseness, highlighting key moments).
4.  **Video Editing**: Based on the final set of transcript segments (either the full speech transcript or the AI-refined segments), the original video is cut and the selected segments are concatenated to produce a new, edited video file.
5.  **Output**: The application provides the processed video, the full transcript, and optionally the AI-processed segment list and speech-only audio.

## Project Structure

The project is organized as follows:

*   **`app/`**: Contains the core application logic.
    *   **`main.py`**: The main FastAPI application. It defines API endpoints, handles file uploads, orchestrates the workflow (transcription, Gemini processing, video cutting), and manages logging. It also performs a CUDA availability check on startup.
    *   **`whisper_utils.py`**: Handles all aspects related to audio transcription using the OpenAI Whisper model. This includes audio extraction, its own silence detection logic, and generating timestamped transcript segments.
    *   **`gemini.py`**: Contains the logic for interacting with the Google Gemini Pro API. It takes transcript segments and a user prompt to return a filtered list of segments.
    *   **`ffmpeg_utils.py`**: Provides utility functions for video and audio manipulation using `ffmpeg-python`, primarily for cutting and concatenating video segments.
*   **`uploads/`**: Default directory for storing uploaded video files.
*   **`processed/`**: Default directory for storing the final, edited video files.
*   **`transcripts/`**: Default directory for storing JSON files of the generated transcripts and Gemini-processed segment lists.
*   **`processed_audio/`**: Default directory for storing extracted speech-only audio files.
*   **`.venv/`**: (Typically) Virtual environment directory (user-managed).
*   **`requirements.txt`**: Lists the Python dependencies for the project.
*   **`app.log`**: Log file for the application.
*   **`README.md`**: This file, providing an overview of the project.

## Setup and Usage

1.  **Create and activate a virtual environment.**
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Environment Variables**: Ensure necessary environment variables are set (e.g., `GEMINI_API_KEY` for Gemini Pro API access). This project uses `python-dotenv` to load variables from a `.env` file.
4.  **Run the application**:
    ```bash
    uvicorn app.main:app --reload
    ```
    (Or your preferred method for running a FastAPI application).
5.  **Interact with the API**: Use an API client (like Postman, curl, or a custom script) to send requests to the `/process` endpoint.

## Key Technologies

*   **Python 3**
*   **FastAPI**: For building the web API.
*   **Uvicorn**: ASGI server to run the FastAPI application.
*   **OpenAI Whisper**: For audio transcription.
*   **Google Gemini Pro**: For AI-powered transcript processing.
*   **FFmpeg (via `ffmpeg-python`)**: For video and audio manipulation.
*   **Pydantic**: For data validation.
*   **Torch**: Dependency for Whisper, with CUDA support for GPU acceleration. 