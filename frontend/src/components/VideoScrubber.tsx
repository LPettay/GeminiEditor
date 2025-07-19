import { Box, Typography, Stack } from '@mui/material';
import { useEffect, useRef, useState, useCallback } from 'react';
import React from 'react';

// Format seconds -> HH:MM:SS
const fmt = (s: number) => {
  if (!Number.isFinite(s)) return '00:00:00';
  const d = new Date(Math.round(s) * 1000);
  return d.toISOString().substring(11, 19);
};

interface Props {
  videoUrl: string;
  onRangeChange: (start: number, end: number) => void;
}

const VideoScrubber: React.FC<Props> = ({ videoUrl, onRangeChange }) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const sliderRef = useRef<HTMLDivElement | null>(null);
  const [duration, setDuration] = useState(0);
  const [range, setRange] = useState<[number, number]>([0, 0]);
  const [currentTime, setCurrentTime] = useState(0);
  const [readyState, setReadyState] = useState(0);
  const [isSeeking, setIsSeeking] = useState(false);
  const [isDragging, setIsDragging] = useState<'start' | 'end' | null>(null);
  const [lastSeekTime, setLastSeekTime] = useState(0);

  // Debug the video URL
  useEffect(() => {
    console.log('VideoScrubber: videoUrl =', videoUrl);
  }, [videoUrl]);

  // Optimized seeking function with throttling
  const seekTo = useCallback((time: number) => {
    const video = videoRef.current;
    if (!video || !Number.isFinite(time)) return;
    
    // Throttle seeking to prevent too many concurrent requests
    if (isSeeking) {
      return; // Skip if already seeking
    }
    
    // Use requestAnimationFrame to make seeking non-blocking
    requestAnimationFrame(() => {
      // Pause video during seeking to prevent unnecessary buffering
      const wasPlaying = !video.paused;
      if (wasPlaying) {
        video.pause();
      }
      
      setIsSeeking(true);
      video.currentTime = time;
      
      // Resume playback if it was playing before
      if (wasPlaying) {
        // Small delay to ensure seeking completes
        setTimeout(() => {
          video.play().catch(console.error);
        }, 100);
      }
    });
  }, [isSeeking]);

  // Load metadata
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    
    console.log('VideoScrubber: Setting up video element listeners');
    
    const onLoaded = () => {
      console.log('Video loaded metadata:', {
        duration: v.duration,
        readyState: v.readyState,
        networkState: v.networkState,
        buffered: v.buffered.length > 0 ? `${v.buffered.start(0)}-${v.buffered.end(0)}` : 'none'
      });
      setDuration(v.duration);
      setRange([0, v.duration]);
      onRangeChange(0, v.duration);
    };
    
    const onCanPlay = () => {
      console.log('Video can play, readyState:', v.readyState);
      setReadyState(v.readyState);
    };
    
    const onTimeUpdate = () => {
      setCurrentTime(v.currentTime);
    };
    
    const onSeeking = () => {
      console.log('Seeking to:', v.currentTime);
      setIsSeeking(true);
    };
    
    const onSeeked = () => {
      console.log('Seeked to:', v.currentTime);
      setIsSeeking(false);
    };
    
    const onError = (e: Event) => {
      console.error('Video error:', e);
      console.error('Video error details:', v.error);
      setIsSeeking(false);
    };
    
    v.addEventListener('loadedmetadata', onLoaded);
    v.addEventListener('canplay', onCanPlay);
    v.addEventListener('timeupdate', onTimeUpdate);
    v.addEventListener('seeking', onSeeking);
    v.addEventListener('seeked', onSeeked);
    v.addEventListener('error', onError);
    
    return () => {
      v.removeEventListener('loadedmetadata', onLoaded);
      v.removeEventListener('canplay', onCanPlay);
      v.removeEventListener('timeupdate', onTimeUpdate);
      v.removeEventListener('seeking', onSeeking);
      v.removeEventListener('seeked', onSeeked);
      v.removeEventListener('error', onError);
    };
  }, [videoUrl, onRangeChange]);

  // Custom slider mouse handlers
  const handleMouseDown = useCallback((e: React.MouseEvent, thumb: 'start' | 'end') => {
    console.log('Mouse down on thumb:', thumb);
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(thumb);
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging || !sliderRef.current) return;
    
    console.log('Mouse move, dragging:', isDragging);
    e.preventDefault();
    
    const rect = sliderRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percentage = Math.max(0, Math.min(1, x / rect.width));
    const time = percentage * duration;
    
    if (isDragging === 'start') {
      const newStart = Math.min(time, range[1] - 1);
      setRange([newStart, range[1]]);
      onRangeChange(newStart, range[1]);
      
      // Throttle real-time seeking during dragging (max 10 times per second)
      const now = Date.now();
      if (now - lastSeekTime > 100) { // 100ms = 10 times per second
        setLastSeekTime(now);
        const video = videoRef.current;
        if (video) {
          video.currentTime = newStart;
        }
      }
    } else {
      const newEnd = Math.max(time, range[0] + 1);
      setRange([range[0], newEnd]);
      onRangeChange(range[0], newEnd);
      
      // Also seek to the out point for visual feedback
      const now = Date.now();
      if (now - lastSeekTime > 100) { // 100ms = 10 times per second
        setLastSeekTime(now);
        const video = videoRef.current;
        if (video) {
          video.currentTime = newEnd;
        }
      }
    }
  }, [isDragging, duration, range, onRangeChange, lastSeekTime]);

  const handleMouseUp = useCallback((e: MouseEvent) => {
    console.log('Mouse up');
    e.preventDefault();
    setIsDragging(null);
  }, []);

  // Set up and clean up event listeners when dragging state changes
  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    } else {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  return (
    <Stack spacing={2} width="100%">
      <video 
        key={videoUrl} 
        ref={videoRef} 
        src={videoUrl} 
        controls 
        style={{ width: '100%' }}
        crossOrigin="anonymous"
        // Optimized video attributes for better buffering
        preload="auto"
        onLoadStart={() => console.log('Video load started')}
        onLoad={() => console.log('Video loaded')}
        onLoadedData={() => console.log('Video loaded data')}
        onLoadedMetadata={() => console.log('Video loaded metadata')}
        onCanPlay={() => console.log('Video can play')}
        onCanPlayThrough={() => console.log('Video can play through')}
        onError={(e) => {
          console.error('Video error event:', e);
          console.error('Video error details:', videoRef.current?.error);
          console.error('Video network state:', videoRef.current?.networkState);
          console.error('Video ready state:', videoRef.current?.readyState);
        }}
      />
      
      {/* Debug info */}
      <Box sx={{ p: 1, bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 1 }}>
        <Typography variant="caption" display="block">
          Video URL: {videoUrl}
        </Typography>
        <Typography variant="caption" display="block">
          Current Time: {fmt(currentTime)} / Duration: {fmt(duration)}
        </Typography>
        <Typography variant="caption" display="block">
          Ready State: {readyState} (0=nothing, 1=metadata, 2=current data, 3=future data, 4=enough data)
        </Typography>
        <Typography variant="caption" display="block">
          Seeking: {isSeeking ? 'Yes' : 'No'}
        </Typography>
      </Box>
      
      {duration > 0 && (
        <>
          {/* Custom range slider */}
          <Box
            ref={sliderRef}
            sx={{
              position: 'relative',
              width: '100%',
              height: 40,
              bgcolor: 'rgba(255,255,255,0.1)',
              borderRadius: 1,
              cursor: 'pointer',
            }}
          >
            {/* Track */}
            <Box
              sx={{
                position: 'absolute',
                top: '50%',
                left: 0,
                right: 0,
                height: 4,
                bgcolor: 'rgba(255,255,255,0.3)',
                borderRadius: 2,
                transform: 'translateY(-50%)',
              }}
            />
            
            {/* Selected range */}
            <Box
              sx={{
                position: 'absolute',
                top: '50%',
                left: `${(range[0] / duration) * 100}%`,
                right: `${100 - (range[1] / duration) * 100}%`,
                height: 4,
                bgcolor: 'primary.main',
                borderRadius: 2,
                transform: 'translateY(-50%)',
              }}
            />
            
            {/* Start thumb */}
            <Box
              sx={{
                position: 'absolute',
                top: '50%',
                left: `${(range[0] / duration) * 100}%`,
                width: 16,
                height: 16,
                bgcolor: 'primary.main',
                borderRadius: '50%',
                transform: 'translate(-50%, -50%)',
                cursor: 'grab',
                '&:active': {
                  cursor: 'grabbing',
                },
              }}
              onMouseDown={(e) => handleMouseDown(e, 'start')}
            />
            
            {/* End thumb */}
            <Box
              sx={{
                position: 'absolute',
                top: '50%',
                left: `${(range[1] / duration) * 100}%`,
                width: 16,
                height: 16,
                bgcolor: 'primary.main',
                borderRadius: '50%',
                transform: 'translate(-50%, -50%)',
                cursor: 'grab',
                '&:active': {
                  cursor: 'grabbing',
                },
              }}
              onMouseDown={(e) => handleMouseDown(e, 'end')}
            />
          </Box>
          
          <Box display="flex" justifyContent="space-between">
            <Typography variant="body2">In {fmt(range[0])}</Typography>
            <Typography variant="body2">Out {fmt(range[1])}</Typography>
          </Box>
        </>
      )}
    </Stack>
  );
};

export default VideoScrubber; 