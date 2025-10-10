"""
Migration script to convert existing files to database records.
This script scans uploads/, transcripts/, and processed/ directories
and creates appropriate database entries.
"""

import sys
import os
from pathlib import Path
import json
import re
from datetime import datetime

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal, init_db
from app.dao import ProjectDAO, SourceVideoDAO, TranscriptSegmentDAO, EditDAO, EditDecisionDAO
from app.models import Project, SourceVideo, TranscriptSegment, Edit, EditDecision
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Directory paths
UPLOAD_DIR = "uploads"
TRANSCRIPTS_DIR = "transcripts"
PROCESSED_DIR = "processed"
PROCESSED_AUDIO_DIR = "processed_audio"


def get_file_info(file_path: str) -> dict:
    """Get basic file information."""
    if not os.path.exists(file_path):
        return {}
    
    stat = os.stat(file_path)
    return {
        'size': stat.st_size,
        'created': datetime.fromtimestamp(stat.st_ctime),
        'modified': datetime.fromtimestamp(stat.st_mtime)
    }


def parse_filename(filename: str) -> dict:
    """
    Parse the filename to extract metadata.
    Format examples:
    - p1-1.mp4 (simple)
    - 5d228c31-72e0-4171-be14-9e420f318a52_p1-1.mp4 (with ID)
    - 5d228c31-72e0-4171-be14-9e420f318a52_p1-1_scope_0-7034.mp4 (with scope)
    """
    base_name = os.path.splitext(filename)[0]
    
    # Extract UUID if present
    uuid_pattern = r'^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_'
    uuid_match = re.match(uuid_pattern, base_name)
    file_id = uuid_match.group(1) if uuid_match else None
    
    # Extract base video name
    if file_id:
        remaining = base_name[len(file_id) + 1:]
    else:
        remaining = base_name
    
    # Extract scope information
    scope_pattern = r'_scope_(\d+)-(\d+)'
    scope_matches = re.findall(scope_pattern, remaining)
    
    # Get the base name without scope info
    base_video_name = re.sub(scope_pattern, '', remaining)
    
    return {
        'file_id': file_id,
        'base_name': base_video_name,
        'scopes': [(int(s), int(e)) for s, e in scope_matches],
        'has_scope': len(scope_matches) > 0
    }


def find_transcript_for_video(video_filename: str) -> str:
    """Find the transcript file for a video."""
    base_name = os.path.splitext(video_filename)[0]
    
    # Look for JSON transcript
    transcript_path = os.path.join(TRANSCRIPTS_DIR, f"{base_name}_transcript.json")
    if os.path.exists(transcript_path):
        return transcript_path
    
    # Try without the extension variations
    parsed = parse_filename(video_filename)
    if parsed['base_name']:
        transcript_path = os.path.join(TRANSCRIPTS_DIR, f"{parsed['base_name']}_transcript.json")
        if os.path.exists(transcript_path):
            return transcript_path
    
    return None


def load_transcript(transcript_path: str) -> list:
    """Load transcript segments from JSON file."""
    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Handle different transcript formats
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and 'segments' in data:
            return data['segments']
        else:
            logger.warning(f"Unknown transcript format in {transcript_path}")
            return []
    except Exception as e:
        logger.error(f"Error loading transcript {transcript_path}: {e}")
        return []


def migrate_source_videos(db, default_project_id: str) -> dict:
    """
    Migrate uploaded videos to database.
    Returns a mapping of filename -> source_video_id
    """
    logger.info("\n" + "="*60)
    logger.info("Migrating Source Videos")
    logger.info("="*60)
    
    if not os.path.exists(UPLOAD_DIR):
        logger.warning(f"Upload directory not found: {UPLOAD_DIR}")
        return {}
    
    video_mapping = {}
    video_files = [f for f in os.listdir(UPLOAD_DIR) if f.endswith(('.mp4', '.avi', '.mov', '.mkv'))]
    
    logger.info(f"Found {len(video_files)} video files in {UPLOAD_DIR}")
    
    for filename in video_files:
        file_path = os.path.join(UPLOAD_DIR, filename)
        file_info = get_file_info(file_path)
        parsed = parse_filename(filename)
        
        # Check if already exists
        existing = db.query(SourceVideo).filter(SourceVideo.file_path == file_path).first()
        if existing:
            logger.info(f"  ✓ Already exists: {filename}")
            video_mapping[filename] = existing.id
            continue
        
        # Create source video record
        logger.info(f"  → Importing: {filename}")
        
        source_video = SourceVideoDAO.create(
            db=db,
            project_id=default_project_id,
            filename=filename,
            file_path=file_path,
            file_size=file_info.get('size')
        )
        
        video_mapping[filename] = source_video.id
        
        # Try to find and import transcript
        transcript_path = find_transcript_for_video(filename)
        if transcript_path:
            logger.info(f"    → Found transcript: {os.path.basename(transcript_path)}")
            segments = load_transcript(transcript_path)
            
            if segments:
                # Update video with transcript path
                SourceVideoDAO.update(db, source_video.id, transcript_path=transcript_path)
                
                # Import transcript segments
                logger.info(f"    → Importing {len(segments)} transcript segments")
                TranscriptSegmentDAO.create_many(db, source_video.id, segments)
        
        logger.info(f"  ✓ Imported: {filename} (ID: {source_video.id})")
    
    logger.info(f"\n✅ Imported {len(video_mapping)} source videos")
    return video_mapping


def migrate_processed_videos(db, default_project_id: str, video_mapping: dict):
    """
    Scan processed videos and try to associate them with source videos.
    Note: This is complex because processed videos may be the result of multiple processing steps.
    For now, we'll just log them for manual review.
    """
    logger.info("\n" + "="*60)
    logger.info("Scanning Processed Videos")
    logger.info("="*60)
    
    if not os.path.exists(PROCESSED_DIR):
        logger.warning(f"Processed directory not found: {PROCESSED_DIR}")
        return
    
    processed_files = [f for f in os.listdir(PROCESSED_DIR) if f.endswith(('.mp4', '.avi', '.mov', '.mkv'))]
    
    logger.info(f"Found {len(processed_files)} processed video files")
    logger.info("\nℹ️  Processed videos will need to be associated with edits manually.")
    logger.info("   These files represent AI-edited outputs from previous runs.\n")
    
    for filename in processed_files:
        parsed = parse_filename(filename)
        logger.info(f"  • {filename}")
        logger.info(f"    Base: {parsed['base_name']}, Scopes: {parsed['scopes']}")


def create_default_project(db) -> str:
    """Create a default project for migrated files."""
    # Check if default project already exists
    existing = db.query(Project).filter(Project.name == "Migrated Content").first()
    if existing:
        logger.info(f"Using existing 'Migrated Content' project (ID: {existing.id})")
        return existing.id
    
    logger.info("Creating default 'Migrated Content' project...")
    project = ProjectDAO.create(
        db=db,
        name="Migrated Content",
        description="Files imported from the legacy file-based system. You can organize these into separate projects.",
        settings={
            "migrated": True,
            "migration_date": datetime.utcnow().isoformat()
        }
    )
    logger.info(f"✓ Created project 'Migrated Content' (ID: {project.id})")
    return project.id


def main():
    """Run the migration."""
    print("\n" + "="*60)
    print("GeminiEditor File Migration")
    print("="*60)
    print("\nThis script will:")
    print("  1. Create a default project for migrated content")
    print("  2. Import videos from uploads/ directory")
    print("  3. Import transcripts from transcripts/ directory")
    print("  4. Scan processed/ directory for reference")
    print("\n" + "="*60)
    
    response = input("\nProceed with migration? (yes/no): ")
    if response.lower() != 'yes':
        print("Migration cancelled.")
        return
    
    # Initialize database
    logger.info("\nInitializing database...")
    init_db()
    
    # Create session
    db = SessionLocal()
    
    try:
        # Create default project
        default_project_id = create_default_project(db)
        
        # Migrate source videos
        video_mapping = migrate_source_videos(db, default_project_id)
        
        # Scan processed videos
        migrate_processed_videos(db, default_project_id, video_mapping)
        
        print("\n" + "="*60)
        print("✅ Migration Complete!")
        print("="*60)
        print(f"\nImported {len(video_mapping)} source videos into the database.")
        print("\nNext steps:")
        print("  1. Start the application: uvicorn app.main:app --reload")
        print("  2. Review the 'Migrated Content' project")
        print("  3. Organize videos into separate projects as needed")
        print("  4. Processed videos will need to be associated with edits manually")
        print("\n" + "="*60)
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        db.rollback()
        print("\n❌ Migration failed. Check the logs above for details.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

