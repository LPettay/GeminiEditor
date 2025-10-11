"""
EDL Stream Service - Builds a single continuous HLS (CMAF fMP4) stream for an Edit's EDL.
Cache by EDL hash: tmp/edl/{hash}/manifest.m3u8
"""

import asyncio
import hashlib
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional

from app.dao import EditDAO, SourceVideoDAO

logger = logging.getLogger(__name__)


@dataclass
class EdlBuildResult:
    success: bool
    edl_hash: str
    message: str = ""


EDL_ROOT = Path("tmp") / "edl"
EDL_ROOT.mkdir(parents=True, exist_ok=True)


def _compute_edl_hash(source_video_id: str, ranges: List[Tuple[float, float]]) -> str:
    h = hashlib.sha1()
    h.update(source_video_id.encode("utf-8"))
    for s, e in ranges:
        h.update(f"{s:.3f},{e:.3f};".encode("utf-8"))
    return h.hexdigest()


def _status_path(edl_hash: str) -> Path:
    return EDL_ROOT / edl_hash / "status.json"


def _manifest_path(edl_hash: str) -> Path:
    return EDL_ROOT / edl_hash / "manifest.m3u8"


async def build_unified_hls_for_edit(project_id: str, edit_id: str) -> EdlBuildResult:
    """
    Build continuous HLS for the edit's included, ordered EDL.
    Returns EdlBuildResult with edl_hash.
    """
    logger.info(f"[EDL] Starting build for project={project_id}, edit={edit_id}")
    # Resolve EDL and source
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        edit = EditDAO.get_with_decisions(db, edit_id)
        if not edit or edit.project_id != project_id:
            logger.error(f"[EDL] Edit not found: {edit_id} in project {project_id}")
            return EdlBuildResult(False, edl_hash="", message="Edit not found in project")

        src = SourceVideoDAO.get_by_id(db, edit.source_video_id)
        if not src or not os.path.exists(src.file_path):
            logger.error(f"[EDL] Source video missing: {edit.source_video_id}")
            return EdlBuildResult(False, edl_hash="", message="Source video missing")

        decisions = [d for d in edit.edit_decisions if d.is_included]
        decisions.sort(key=lambda d: d.order_index)
        if not decisions:
            logger.warning(f"[EDL] No included clips in edit {edit_id}")
            return EdlBuildResult(False, edl_hash="", message="No included clips in EDL")

        logger.info(f"[EDL] Found {len(decisions)} clips to concat")
        ranges: List[Tuple[float, float]] = [(float(d.start_time), float(d.end_time)) for d in decisions]
        edl_hash = _compute_edl_hash(edit.source_video_id, ranges)
        logger.info(f"[EDL] Hash: {edl_hash}")
        out_dir = EDL_ROOT / edl_hash
        out_dir.mkdir(parents=True, exist_ok=True)
        status_path = _status_path(edl_hash)
        manifest = _manifest_path(edl_hash)

        # If already built, return
        init_path = out_dir / "init.mp4"
        if manifest.exists() and init_path.exists():
            logger.info(f"[EDL] Already built: {manifest}")
            try:
                status_path.write_text(json.dumps({"status": "ready", "edl_hash": edl_hash}), encoding="utf-8")
            except Exception:
                pass
            return EdlBuildResult(True, edl_hash, message="Already built")
        elif manifest.exists():
            logger.warning(f"[EDL] Manifest exists but init.mp4 missing, rebuilding: {manifest}")

        # Write building status
        logger.info(f"[EDL] Writing building status to {status_path}")
        try:
            status_path.write_text(json.dumps({"status": "building", "edl_hash": edl_hash}), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[EDL] Could not write status: {e}")

        # Step 1: Extract and normalize each range to temp files
        logger.info(f"[EDL] Extracting {len(ranges)} normalized clips")
        temp_clips: List[Path] = []
        for i, (s, e) in enumerate(ranges):
            temp_clip = out_dir / f"temp_{i:05d}.mp4"
            if temp_clip.exists():
                temp_clips.append(temp_clip)
                continue
            
            duration = e - s
            extract_cmd = [
                "ffmpeg", "-nostdin", "-y",
                "-i", src.file_path,
                "-ss", str(s), "-t", str(duration),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-profile:v", "main", "-level", "4.1",
                "-r", "30", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
                "-x264-params", "keyint=60:min-keyint=60:scenecut=0:open-gop=0",
                "-vsync", "cfr",
                "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
                "-fflags", "+genpts", "-avoid_negative_ts", "make_zero",
                str(temp_clip)
            ]
            logger.info(f"[EDL] Extracting clip {i+1}/{len(ranges)}: {s:.2f}-{e:.2f}")
            proc = await asyncio.to_thread(subprocess.run, extract_cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                logger.error(f"[EDL] Clip {i} extraction failed: {proc.stderr}")
                try:
                    status_path.write_text(json.dumps({"status": "failed", "edl_hash": edl_hash, "error": proc.stderr}), encoding="utf-8")
                except Exception:
                    pass
                return EdlBuildResult(False, edl_hash, message=f"Clip extraction failed: {proc.stderr}")
            temp_clips.append(temp_clip)

        # Step 2: Build concat list
        concat_list = out_dir / "concat.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for tc in temp_clips:
                f.write(f"file '{tc.name}'\n")

        logger.info(f"[EDL] Concat {len(temp_clips)} clips via demuxer to HLS")
        
        # Step 3: Concat via demuxer and segment to HLS
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy",
            # HLS CMAF segmentation
            "-f", "hls",
            "-hls_time", "0.5",
            "-hls_playlist_type", "vod",
            "-hls_segment_type", "fmp4",
            "-hls_flags", "independent_segments",
            "-hls_fmp4_init_filename", "init.mp4",
            "-hls_segment_filename", str(out_dir / "seg-%05d.m4s"),
            str(manifest)
        ]

        proc = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            logger.error(f"[EDL] FFmpeg failed: {proc.stderr}")
            try:
                status_path.write_text(json.dumps({"status": "failed", "edl_hash": edl_hash, "error": proc.stderr}), encoding="utf-8")
            except Exception:
                pass
            return EdlBuildResult(False, edl_hash, message=f"FFmpeg failed: {proc.stderr}")

        logger.info(f"[EDL] Build successful: {manifest}")
        try:
            status_path.write_text(json.dumps({"status": "ready", "edl_hash": edl_hash}), encoding="utf-8")
        except Exception:
            pass

        return EdlBuildResult(True, edl_hash, message="Built")
    finally:
        db.close()


async def build_unified_hls_from_ranges(source_video_id: str, source_path: str, ranges: List[Tuple[float, float]]) -> EdlBuildResult:
    """Build unified HLS from raw ranges (for source video clips)."""
    logger.info(f"[EDL] Building from ranges for video {source_video_id}, {len(ranges)} clips")
    
    edl_hash = _compute_edl_hash(source_video_id, ranges)
    out_dir = EDL_ROOT / edl_hash
    out_dir.mkdir(parents=True, exist_ok=True)
    status_path = _status_path(edl_hash)
    manifest = _manifest_path(edl_hash)
    
    init_path = out_dir / "init.mp4"
    if manifest.exists() and init_path.exists():
        logger.info(f"[EDL] Already built: {manifest}")
        try:
            status_path.write_text(json.dumps({"status": "ready", "edl_hash": edl_hash}), encoding="utf-8")
        except Exception:
            pass
        return EdlBuildResult(True, edl_hash, message="Already built")
    elif manifest.exists():
        logger.warning(f"[EDL] Manifest exists but init.mp4 missing, rebuilding: {manifest}")
    
    try:
        status_path.write_text(json.dumps({"status": "building", "edl_hash": edl_hash}), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[EDL] Could not write status: {e}")
    
    # Extract and normalize each range
    logger.info(f"[EDL] Extracting {len(ranges)} normalized clips")
    temp_clips: List[Path] = []
    for i, (s, e) in enumerate(ranges):
        temp_clip = out_dir / f"temp_{i:05d}.mp4"
        if temp_clip.exists():
            temp_clips.append(temp_clip)
            continue
        
        duration = e - s
        extract_cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-i", source_path,
            "-ss", str(s), "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-profile:v", "main", "-level", "4.1",
            "-r", "30", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
            "-x264-params", "keyint=60:min-keyint=60:scenecut=0:open-gop=0",
            "-vsync", "cfr",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
            "-fflags", "+genpts", "-avoid_negative_ts", "make_zero",
            str(temp_clip)
        ]
        logger.info(f"[EDL] Extracting clip {i+1}/{len(ranges)}: {s:.2f}-{e:.2f}")
        proc = await asyncio.to_thread(subprocess.run, extract_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            logger.error(f"[EDL] Clip {i} extraction failed: {proc.stderr}")
            try:
                status_path.write_text(json.dumps({"status": "failed", "edl_hash": edl_hash, "error": proc.stderr}), encoding="utf-8")
            except Exception:
                pass
            return EdlBuildResult(False, edl_hash, message=f"Clip extraction failed")
        temp_clips.append(temp_clip)
    
    # Build concat list
    concat_list = out_dir / "concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for tc in temp_clips:
            f.write(f"file '{tc.name}'\n")
    
    logger.info(f"[EDL] Concat {len(temp_clips)} clips via demuxer to HLS")
    
    # Concat and segment to HLS (run from out_dir, so use relative paths)
    cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-f", "concat", "-safe", "0", "-i", "concat.txt",
        "-c", "copy",
        "-f", "hls",
        "-hls_time", "0.5",
        "-hls_playlist_type", "vod",
        "-hls_segment_type", "fmp4",
        "-hls_flags", "independent_segments",
        "-hls_fmp4_init_filename", "init.mp4",
        "-hls_segment_filename", "seg-%05d.m4s",
        "manifest.m3u8"
    ]
    
    logger.info(f"[EDL] Running concat command: {' '.join(cmd)}")
    logger.info(f"[EDL] Working directory: {os.getcwd()}")
    logger.info(f"[EDL] Output dir: {out_dir}")
    logger.info(f"[EDL] Manifest path: {manifest}")
    proc = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=300, cwd=str(out_dir))
    
    logger.info(f"[EDL] FFmpeg returncode: {proc.returncode}")
    if proc.stdout:
        logger.info(f"[EDL] FFmpeg stdout: {proc.stdout[:500]}")
    if proc.stderr:
        logger.info(f"[EDL] FFmpeg stderr: {proc.stderr[:500]}")
    
    if proc.returncode != 0:
        logger.error(f"[EDL] FFmpeg concat failed with code {proc.returncode}")
        logger.error(f"[EDL] Full stderr: {proc.stderr}")
        try:
            status_path.write_text(json.dumps({"status": "failed", "edl_hash": edl_hash, "error": proc.stderr}), encoding="utf-8")
        except Exception:
            pass
        return EdlBuildResult(False, edl_hash, message=f"Concat failed: {proc.stderr[:200]}")
    
    # Verify files were created
    if not manifest.exists():
        logger.error(f"[EDL] Manifest not created even though FFmpeg returned 0: {manifest}")
        return EdlBuildResult(False, edl_hash, message="Manifest file not created")
    
    init_path = out_dir / "init.mp4"
    if not init_path.exists():
        logger.error(f"[EDL] init.mp4 not created: {init_path}")
        return EdlBuildResult(False, edl_hash, message="Init file not created")
    
    seg_count = len(list(out_dir.glob("seg-*.m4s")))
    logger.info(f"[EDL] Build successful: {manifest}, {seg_count} segments, init size: {init_path.stat().st_size}")
    
    try:
        status_path.write_text(json.dumps({"status": "ready", "edl_hash": edl_hash}), encoding="utf-8")
    except Exception:
        pass
    
    return EdlBuildResult(True, edl_hash, message="Built")


