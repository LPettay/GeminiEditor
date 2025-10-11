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

# Builder version for cache invalidation
BUILDER_VERSION = "2"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _clip_output_paths(base_dir: Path, decision_id: str) -> Tuple[Path, str, Path]:
    """
    Returns (init_mp4, segment_filename_pattern, per_clip_m3u8) for a decision.
    """
    init_path = base_dir / f"dec_{decision_id}.init.mp4"
    seg_pattern = f"dec_{decision_id}-%05d.m4s"
    m3u8_path = base_dir / f"dec_{decision_id}.m3u8"
    return init_path, seg_pattern, m3u8_path


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

    init_path, seg_pattern, m3u8_path = _clip_output_paths(base_dir, decision_id)
    version_path = base_dir / "version.txt"

    # If playlist and init exist and version matches, reuse
    if (
        init_path.exists() and m3u8_path.exists() and init_path.stat().st_size > 0 and m3u8_path.stat().st_size > 0
        and version_path.exists() and version_path.read_text(encoding="utf-8").strip() == BUILDER_VERSION
    ):
        return str(init_path), str(m3u8_path)

    # Build CMAF fMP4 with micro-fragments (no single_file). Force keyframe at start, CFR, fixed GOP.
    cmd = [
        "ffmpeg", "-nostdin", "-y",
        # Accurate seek: apply -ss after input for frame-accurate cuts
        "-i", source_video_path,
        "-ss", str(start_time),
        "-t", str(duration),
        "-analyzeduration", "0", "-probesize", "1024k",
        "-fflags", "+genpts",
        "-avoid_negative_ts", "make_zero",
        "-muxpreload", "0",
        "-muxdelay", "0",
        "-c:v", VIDEO_CODEC,
        "-profile:v", VIDEO_PROFILE,
        "-level:v", VIDEO_LEVEL,
        "-pix_fmt", PIX_FMT,
        "-r", str(FRAMERATE),
        "-g", str(GOP),
        "-keyint_min", str(GOP),
        "-sc_threshold", "0",
        "-x264-params", f"keyint={GOP}:min-keyint={GOP}:scenecut=0:open-gop=0",
        # Keyframe at clip start; also align to fragment cadence (~0.5s)
        "-force_key_frames", "expr:gte(t,n_forced*0.5)",
        "-vsync", "cfr",
        "-video_track_timescale", "90000",
        "-map", "0:v:0",
        "-map", "0:a:0",
        "-c:a", AUDIO_CODEC,
        "-b:a", AUDIO_BITRATE,
        "-ar", str(AUDIO_RATE),
        "-ac", str(AUDIO_CHANNELS),
        "-f", "hls",
        "-hls_time", "0.5",
        "-hls_playlist_type", "vod",
        "-hls_list_size", "0",
        "-hls_flags", "independent_segments",
        "-hls_segment_type", "fmp4",
        "-hls_fmp4_init_filename", init_path.name,
        "-hls_segment_filename", str(base_dir / seg_pattern),
        str(m3u8_path)
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed building CMAF for decision {decision_id}: {proc.stderr}"
        )

    # Sanity check files exist
    if not (init_path.exists() and m3u8_path.exists()):
        raise RuntimeError(
            f"CMAF outputs missing for decision {decision_id}: {init_path} / {m3u8_path}"
        )

    # Write builder version for cache validation
    try:
        version_path.write_text(BUILDER_VERSION, encoding="utf-8")
    except Exception:
        pass

    return str(init_path), str(m3u8_path)


def build_playlist_content(
    project_id: str,
    edit_id: str,
    items: List[Tuple[str, float]]
) -> str:
    """
    Build an HLS VOD playlist where each item is (decision_id, duration_seconds).
    URIs reference API endpoints that serve the init and media files.
    """
    # We will compute target duration based on parsed fragment durations
    all_durations: List[float] = []

    lines: List[str] = []
    lines.append("#EXTM3U")
    lines.append("#EXT-X-VERSION:7")
    lines.append("#EXT-X-TARGETDURATION:" + str(target_duration))
    lines.append("#EXT-X-MEDIA-SEQUENCE:0")
    lines.append("#EXT-X-PLAYLIST-TYPE:VOD")
    lines.append("#EXT-X-INDEPENDENT-SEGMENTS")

    base_dir = Path("tmp") / "hls" / edit_id / "segments"
    for index, (decision_id, _duration) in enumerate(items):
        # Read per-clip m3u8 and inline its fragments
        per_clip_m3u8 = base_dir / f"dec_{decision_id}.m3u8"
        if index > 0:
            lines.append("#EXT-X-DISCONTINUITY")
        lines.append(f"#EXT-X-MAP:URI=\"/api/projects/{project_id}/edits/{edit_id}/segments/dec_{decision_id}.init.mp4\"")
        if per_clip_m3u8.exists():
            with open(per_clip_m3u8, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if line.startswith("#EXTINF:"):
                        # keep duration
                        lines.append(line)
                        try:
                            dur = float(line.split(":",1)[1].split(",")[0])
                            all_durations.append(dur)
                        except Exception:
                            pass
                    elif line and not line.startswith("#"):
                        # It's a segment filename; map to our endpoint
                        seg_name = line
                        lines.append(f"/api/projects/{project_id}/edits/{edit_id}/segments/{seg_name}")
        else:
            # Fallback: single EXTINF using provided duration
            dur = max(0.01, _duration)
            all_durations.append(dur)
            lines.append(f"#EXTINF:{dur:.3f},")
            lines.append(f"/api/projects/{project_id}/edits/{edit_id}/segments/dec_{decision_id}-00000.m4s")

    target_duration = max(1, math.ceil(max(all_durations) if all_durations else 1))
    # Rewrite header target duration after computing
    lines[2] = "#EXT-X-TARGETDURATION:" + str(target_duration)
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


