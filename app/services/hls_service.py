"""
HLS Service - Builds CMAF (fMP4) segments per edit decision and generates a dynamic HLS playlist.

Only applies to newly created videos/edits. Segments are cached under tmp/hls/{edit_id}/.
"""

import os
import math
import subprocess
from pathlib import Path
from typing import Tuple, List


# Encoding parameters for uniform, seamless playback
VIDEO_CODEC = "libx264"
VIDEO_PROFILE = "main"
VIDEO_LEVEL = "4.1"
PIX_FMT = "yuv420p"
FRAMERATE = 30  # fps
GOP = 60        # frames

AUDIO_CODEC = "aac"
AUDIO_RATE = 48000
AUDIO_CHANNELS = 2
AUDIO_BITRATE = "128k"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _clip_output_paths(base_dir: Path, decision_id: str) -> Tuple[Path, Path, Path]:
    """
    Returns (init_mp4, media_m4s, temp_clip_m3u8) paths for a decision.
    """
    init_path = base_dir / f"dec_{decision_id}.init.mp4"
    media_path = base_dir / f"dec_{decision_id}.m4s"
    # ffmpeg will write a small per-clip playlist we can ignore
    m3u8_path = base_dir / f"dec_{decision_id}.m3u8"
    return init_path, media_path, m3u8_path


def ensure_cmaf_for_decision(
    edit_id: str,
    decision_id: str,
    source_video_path: str,
    start_time: float,
    end_time: float,
) -> Tuple[str, str]:
    """
    Ensure CMAF (init.mp4 + single .m4s) exists on disk for a given edit decision.
    Returns (init_path_str, media_path_str).
    """
    duration = max(0.01, end_time - start_time)

    base_dir = Path("tmp") / "hls" / edit_id / "segments"
    _ensure_dir(base_dir)

    init_path, media_path, m3u8_path = _clip_output_paths(base_dir, decision_id)

    # If both files already exist and are non-empty, reuse
    if init_path.exists() and media_path.exists() and init_path.stat().st_size > 0 and media_path.stat().st_size > 0:
        return str(init_path), str(media_path)

    # Build CMAF pair using ffmpeg HLS (fMP4 single_file)
    # We intentionally force keyframe at boundaries and fixed GOP to guarantee seamless transitions.
    cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-ss", str(start_time),
        "-t", str(duration),
        "-i", source_video_path,
        "-analyzeduration", "0", "-probesize", "1024k",
        "-c:v", VIDEO_CODEC,
        "-profile:v", VIDEO_PROFILE,
        "-level:v", VIDEO_LEVEL,
        "-pix_fmt", PIX_FMT,
        "-r", str(FRAMERATE),
        "-g", str(GOP),
        "-keyint_min", str(GOP),
        "-sc_threshold", "0",
        "-x264-params", f"keyint={GOP}:min-keyint={GOP}:scenecut=0:open-gop=0",
        "-c:a", AUDIO_CODEC,
        "-b:a", AUDIO_BITRATE,
        "-ar", str(AUDIO_RATE),
        "-ac", str(AUDIO_CHANNELS),
        "-f", "hls",
        "-hls_time", str(duration),               # single segment equal to clip duration
        "-hls_playlist_type", "vod",
        "-hls_list_size", "0",
        "-hls_flags", "single_file+independent_segments",
        "-hls_segment_type", "fmp4",
        "-hls_fmp4_init_filename", init_path.name,
        "-hls_segment_filename", media_path.name,
        str(m3u8_path)
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed building CMAF for decision {decision_id}: {proc.stderr}"
        )

    # Sanity check files exist
    if not (init_path.exists() and media_path.exists()):
        raise RuntimeError(
            f"CMAF outputs missing for decision {decision_id}: {init_path} / {media_path}"
        )

    return str(init_path), str(media_path)


def build_playlist_content(
    project_id: str,
    edit_id: str,
    items: List[Tuple[str, float]]
) -> str:
    """
    Build an HLS VOD playlist where each item is (decision_id, duration_seconds).
    URIs reference API endpoints that serve the init and media files.
    """
    target_duration = max(1, math.ceil(max((d for _, d in items), default=1)))

    lines: List[str] = []
    lines.append("#EXTM3U")
    lines.append("#EXT-X-VERSION:7")
    lines.append("#EXT-X-TARGETDURATION:" + str(target_duration))
    lines.append("#EXT-X-MEDIA-SEQUENCE:0")
    lines.append("#EXT-X-PLAYLIST-TYPE:VOD")
    lines.append("#EXT-X-INDEPENDENT-SEGMENTS")

    for decision_id, duration in items:
        lines.append(
            f"#EXT-X-MAP:URI=\"/api/projects/{project_id}/edits/{edit_id}/segments/{decision_id}.init\""
        )
        lines.append(f"#EXTINF:{duration:.3f},")
        lines.append(
            f"/api/projects/{project_id}/edits/{edit_id}/segments/{decision_id}.m4s"
        )

    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


