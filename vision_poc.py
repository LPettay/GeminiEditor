import argparse
import os
import json
import google.generativeai as genai
import subprocess
import tempfile
import datetime
import logging

# Optional – we reuse the project's Whisper helper if available
try:
    from app.whisper_utils import transcribe_video
except ImportError:
    transcribe_video = None  # Fallback later

# ------------------------------ LOGGER -------------------------------------

logger = logging.getLogger("vision_poc")

MODEL_NAME = "models/gemini-2.5-flash"

# -------------------------------- PROMPTS ----------------------------------

# Prompt issued to Gemini when it must decide whether more visual context
# *inside the provided clip* is needed to support the quoted voice-line.
PROMPT_SELECT_IN_CLIP = (
    "You are refining the start/end boundaries of an interesting spoken line. "
    "Inputs you receive:\n"
    "• A gameplay video clip.\n"
    "• A JSON *metadata* block telling you where the spoken words occur *inside* the clip.\n"
    "• The text of the spoken line.\n\n"
    "Rules:\n"
    "1️⃣ Stay strictly INSIDE the clip — do NOT request frames that lie before 0 or after clip_end.\n"
    "2️⃣ Decide whether extra visuals immediately *before* or *after* the spoken words will help viewers understand the action.\n"
    "3️⃣ Return **only** this JSON schema (no markdown, no commentary):\n"
    "{\"delta_before\": int, \"delta_after\": int, \"reason\": string}\n"
    "• delta_before / delta_after are whole-second integers 0–padding (see metadata).\n"
    "• reason ≤ 25 words."
)


# ------------------------------ HELPERS ------------------------------------

def generate_transcript_local(video_path: str) -> str | None:
    """Generate a simple timestamped transcript using the project's Whisper helper."""
    if transcribe_video is None:
        logger.warning("app.whisper_utils not available – skipping auto-transcription.")
        return None

    try:
        result = transcribe_video(video_path, model_name="base", language="en")
        lines = []
        for seg in result.get("segments", []):
            lines.append(f"{seg['start']:.2f}-{seg['end']:.2f} {seg['text']}")
        return "\n".join(lines)
    except Exception as e:
        print(f"[WARN] Transcript generation failed: {e}")
        return None


def call_gemini_vision(api_key: str, video_path: str, metadata_json: str, transcript: str):
    """Send clip, metadata, transcript, and prompt to Gemini Vision."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL_NAME)

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    # Build content: video first, then metadata, transcript, then prompt (per docs)
    content: list[object] = [
        {"mime_type": "video/mp4", "data": video_bytes},
        f"metadata:\n{metadata_json}",
        f"voice_line_transcript:\n{transcript}",
        PROMPT_SELECT_IN_CLIP,
    ]

    logger.info("Sending content to Gemini Vision ...")
    logger.info(f"  Video bytes   : {len(video_bytes)}")
    logger.info(f"  Metadata bytes: {len(metadata_json)}")
    logger.info(f"  Transcript len: {len(transcript)}")

    response = model.generate_content(content)
    logger.info("Gemini response received (raw):")
    logger.info(response.text.strip())
    print(response.text.strip())


def main():
    parser = argparse.ArgumentParser(description="Gemini Vision summary of a video segment")
    parser.add_argument("video", help="Path to a video file (e.g. .mp4)")
    parser.add_argument("voice_start", type=float, help="Start time (s) of the spoken line in the ORIGINAL video")
    parser.add_argument("voice_end", type=float, help="End time (s) of the spoken line in the ORIGINAL video")
    parser.add_argument("--padding", type=float, default=2.0, help="Seconds of visual padding to include before and after the spoken line when extracting the clip")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary extracted clip instead of deleting it")
    parser.add_argument("--transcript", help="Provide an exact transcript for the voice line. If omitted, Whisper will attempt to generate one.")
    parser.add_argument("--api_key", help="Gemini API key (or set GEMINI_API_KEY env var)")
    args = parser.parse_args()

    # Configure logging level (default INFO). Allow override via env or arg later.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    api_key = args.api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        parser.error("API key required via --api_key or GEMINI_API_KEY env var")

    # Calculate clip boundaries with padding, ensuring non-negative start
    clip_start = max(0.0, args.voice_start - args.padding)
    clip_end = args.voice_end + args.padding

    # Prepare tmp directory
    tmp_dir = os.path.join(os.path.dirname(__file__), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    # Generate timestamp for readable filenames
    timestamp_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    voice_clip_path = os.path.join(tmp_dir, f"voice_{timestamp_tag}.mp4")

    ffmpeg_voice_cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-ss", str(args.voice_start),
        "-to", str(args.voice_end),
        "-i", args.video,
        "-c", "copy",
        voice_clip_path,
    ]

    # 2. Extract **padded** clip
    padded_clip_path = os.path.join(tmp_dir, f"padded_{timestamp_tag}.mp4")

    ffmpeg_pad_cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-ss", str(clip_start),
        "-to", str(clip_end),
        "-i", args.video,
        "-c", "copy",
        padded_clip_path,
    ]

    try:
        # Run FFmpeg extractions
        subprocess.run(ffmpeg_voice_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        subprocess.run(ffmpeg_pad_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # Generate transcript if not provided
        transcript = args.transcript
        if transcript is None:
            transcript = generate_transcript_local(voice_clip_path)
            if transcript is None:
                logger.warning("Could not generate transcript, proceeding without it.")
                transcript = "" # Ensure transcript is not None for the call

        # Generate metadata JSON (all times are RELATIVE TO CLIP START = 0)
        voice_start_clip = args.voice_start - clip_start
        voice_end_clip = args.voice_end - clip_start
        clip_len = clip_end - clip_start

        metadata_json = json.dumps({
            "voice_start": round(voice_start_clip, 2),
            "voice_end": round(voice_end_clip, 2),
            "clip_len": round(clip_len, 2),
            "padding": args.padding
        })

        # Log what we will send
        logger.info("Prepared clip for Gemini:")
        logger.info(f"  Original video: {args.video}")
        logger.info(f"  Voice-only clip: {voice_clip_path}")
        logger.info(f"  Padded clip   : {padded_clip_path}")
        logger.info(f"  Voice line rel: {voice_start_clip:.2f}s – {voice_end_clip:.2f}s (len {voice_end_clip - voice_start_clip:.2f}s)")
        logger.info(f"  Padding used  : {args.padding}s; clip length {clip_len:.2f}s")
        logger.info(f"  Transcript chars: {len(transcript)}")
        logger.info(f"  Metadata JSON : {metadata_json}")

        call_gemini_vision(api_key, padded_clip_path, metadata_json, transcript)
    finally:
        if not args.keep:
            try:
                os.remove(voice_clip_path)
            except FileNotFoundError:
                pass
            try:
                os.remove(padded_clip_path)
            except FileNotFoundError:
                pass
        else:
            logger.info(f"[Saved voice-only clip ] {voice_clip_path}")
            logger.info(f"[Saved padded clip     ] {padded_clip_path}")


if __name__ == "__main__":
    main() 