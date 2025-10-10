"""
Video Streaming Service - Modular video streaming with range request support.
This service can be used by any endpoint that needs to stream video files.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Generator
from fastapi import Request, HTTPException, status
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

class VideoStreamingService:
    """Service for streaming video files with optimized range request support."""
    
    # Optimized chunk size for video streaming (64KB chunks for better performance)
    CHUNK_SIZE = 64 * 1024  # 64KB chunks
    
    # Content type mapping
    CONTENT_TYPE_MAP = {
        '.mp4': 'video/mp4',
        '.avi': 'video/x-msvideo',
        '.mov': 'video/quicktime',
        '.mkv': 'video/x-matroska',
        '.webm': 'video/webm',
    }
    
    @classmethod
    def get_content_type(cls, file_path: str) -> str:
        """Determine content type based on file extension."""
        file_extension = Path(file_path).suffix.lower()
        return cls.CONTENT_TYPE_MAP.get(file_extension, 'video/mp4')
    
    @classmethod
    def stream_video_file(
        cls,
        file_path: str,
        filename: str,
        request: Request,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        semaphore: Optional[object] = None
    ) -> StreamingResponse:
        """
        Stream a video file with optimized range request support.
        
        Args:
            file_path: Path to the video file
            filename: Display filename for the video
            request: FastAPI request object (used for range headers)
            semaphore: Optional semaphore for limiting concurrent streams
            
        Returns:
            StreamingResponse with proper headers and range support
        """
        # Validate file exists
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video file not found"
            )
        
        file_size = os.path.getsize(file_path)
        content_type = cls.get_content_type(file_path)
        range_header = request.headers.get("range")
        
        logger.info(f"Streaming video: {filename}")
        logger.info(f"File size: {file_size} bytes")
        logger.info(f"Content type: {content_type}")
        logger.info(f"Range header: {range_header}")
        
        if range_header:
            return cls._stream_range_request(file_path, file_size, content_type, filename, range_header)
        else:
            return cls._stream_full_file(file_path, file_size, content_type, filename)
    
    @classmethod
    def _stream_range_request(
        cls,
        file_path: str,
        file_size: int,
        content_type: str,
        filename: str,
        range_header: str
    ) -> StreamingResponse:
        """Handle range requests for partial content streaming."""
        try:
            # Parse range header (e.g., "bytes=0-1023")
            range_type, range_spec = range_header.split("=")
            if range_type.lower() != "bytes":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid range type"
                )
            
            start, end = range_spec.split("-")
            start = int(start) if start else 0
            end = int(end) if end else file_size - 1
            
            # Validate range
            if start >= file_size or end >= file_size or start > end:
                raise HTTPException(
                    status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                    detail="Range not satisfiable"
                )
            
            content_length = end - start + 1
            logger.info(f"Serving range: {start}-{end} ({content_length} bytes)")
            
            def range_generator() -> Generator[bytes, None, None]:
                """Generator for range request data."""
                with open(file_path, "rb") as file_handle:
                    file_handle.seek(start)
                    remaining = content_length
                    while remaining > 0:
                        chunk_size = min(cls.CHUNK_SIZE, remaining)
                        chunk = file_handle.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk
                        remaining -= len(chunk)
            
            return StreamingResponse(
                range_generator(),
                media_type=content_type,
                status_code=status.HTTP_206_PARTIAL_CONTENT,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(content_length),
                    "Accept-Ranges": "bytes",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, HEAD",
                    "Access-Control-Allow-Headers": "Range",
                    "Cache-Control": "public, max-age=3600",
                    "Content-Disposition": f"inline; filename={filename}"
                }
            )
            
        except ValueError as e:
            logger.error(f"Invalid range header format: {range_header}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid range header format"
            )
    
    @classmethod
    def _stream_full_file(
        cls,
        file_path: str,
        file_size: int,
        content_type: str,
        filename: str
    ) -> StreamingResponse:
        """Handle full file streaming with optimized chunking."""
        logger.info("Serving full video file with optimized streaming")
        
        def file_generator() -> Generator[bytes, None, None]:
            """Generator for full file data."""
            with open(file_path, "rb") as file_handle:
                while chunk := file_handle.read(cls.CHUNK_SIZE):
                    yield chunk
        
        return StreamingResponse(
            file_generator(),
            media_type=content_type,
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, HEAD",
                "Access-Control-Allow-Headers": "Range",
                "Cache-Control": "public, max-age=3600",
                "Content-Disposition": f"inline; filename={filename}"
            }
        )


# Convenience function for easy integration
def stream_video_file(file_path: str, filename: str, request: Request, start_time: Optional[float] = None, end_time: Optional[float] = None) -> StreamingResponse:
    """
    Convenience function to stream a video file.
    This is the main entry point for video streaming.
    
    Args:
        file_path: Path to the video file
        filename: Display name for the file
        request: FastAPI request object
        start_time: Optional start time in seconds for clip streaming
        end_time: Optional end time in seconds for clip streaming
    """
    return VideoStreamingService.stream_video_file(file_path, filename, request, start_time, end_time)
