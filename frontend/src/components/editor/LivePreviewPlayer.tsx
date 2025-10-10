/**
 * Live Preview Player - Plays video clips in sequence for pseudo-concatenated preview.
 * This component handles the seamless playback of reordered video segments.
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Box,
  IconButton,
  Typography,
  Slider,
  LinearProgress,
  Alert,
} from '@mui/material';
import {
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  VolumeUp as VolumeUpIcon,
  VolumeOff as VolumeOffIcon,
} from '@mui/icons-material';

interface VideoClip {
  id: string;
  segment_id: string;
  start_time: number;
  end_time: number;
  duration: number;
  order_index: number;
  stream_url: string;
}

interface LivePreviewPlayerProps {
  clips: VideoClip[];
  currentClipIndex: number;
  onClipChange: (index: number) => void;
  onTimeUpdate: (time: number, clipIndex: number) => void;
  className?: string;
  style?: React.CSSProperties;
}

export const LivePreviewPlayer: React.FC<LivePreviewPlayerProps> = ({
  clips,
  currentClipIndex,
  onClipChange,
  onTimeUpdate,
  className,
  style,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const isPlayingRef = useRef(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);

  // Sort clips by order_index to ensure correct playback order
  const sortedClips = [...clips].sort((a, b) => a.order_index - b.order_index);
  const currentClip = sortedClips[currentClipIndex];
  const totalDuration = sortedClips.reduce((sum, clip) => sum + clip.duration, 0);
  
  // Calculate absolute time across all clips for the slider
  const getAbsoluteTime = () => {
    let absoluteTime = 0;
    for (let i = 0; i < currentClipIndex; i++) {
      absoluteTime += sortedClips[i].duration;
    }
    return absoluteTime + currentTime;
  };

  // Load the current clip
  useEffect(() => {
    if (!currentClip || !videoRef.current) return;

    console.log('Loading clip:', currentClipIndex, 'URL:', currentClip.stream_url);
    const wasPlaying = isPlayingRef.current;
    console.log('Loading new clip, wasPlaying:', wasPlaying);
    
    setIsLoading(true);
    setError(null);
    
    // Load the video clip (this will be the full original video)
    videoRef.current.src = currentClip.stream_url;
    
    // Only call load() if we're not trying to maintain playing state
    if (!wasPlaying) {
      videoRef.current.load();
    } else {
      // If we want to maintain playing state, just set the src and let it load naturally
      console.log('Skipping load() to maintain playing state');
      
      // But we still need to call play() after the video loads
      const handleCanPlay = () => {
        console.log('New clip can play, starting autoplay');
        if (videoRef.current && wasPlaying) {
          videoRef.current.play()
            .then(() => {
              console.log('Autoplay after src change successful');
            })
            .catch((error) => {
              console.error('Autoplay after src change failed:', error);
            });
        }
        videoRef.current?.removeEventListener('canplay', handleCanPlay);
      };
      
      videoRef.current.addEventListener('canplay', handleCanPlay);
    }
    
    // Reset time when switching clips
    setCurrentTime(0);
    
  }, [currentClip, currentClipIndex]);

  // Handle video events
  const handleLoadedMetadata = useCallback(() => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration);
      setIsLoading(false);
    }
  }, []);

  const handleTimeUpdate = useCallback(() => {
    if (videoRef.current && currentClip) {
      const videoTime = videoRef.current.currentTime;
      
      // Check if we've reached the end of the current clip
      if (videoTime >= currentClip.end_time) {
        // Auto-advance to next clip
        if (currentClipIndex < clips.length - 1) {
          onClipChange(currentClipIndex + 1);
        } else {
          // End of all clips
          setIsPlaying(false);
          setCurrentTime(0);
          onClipChange(0); // Reset to first clip
        }
        return;
      }
      
      // Calculate time within the current clip
      const clipTime = Math.max(0, videoTime - currentClip.start_time);
      setCurrentTime(clipTime);
      
      // Calculate absolute time across all clips
      let absoluteTime = 0;
      for (let i = 0; i < currentClipIndex; i++) {
        absoluteTime += clips[i].duration;
      }
      absoluteTime += clipTime;
      
      onTimeUpdate(absoluteTime, currentClipIndex);
    }
  }, [currentClipIndex, clips, currentClip, onTimeUpdate]);

  const handleEnded = useCallback(() => {
    // Auto-advance to next clip
    if (currentClipIndex < sortedClips.length - 1) {
      console.log('Clip ended, moving to clip:', currentClipIndex + 1);
      const wasPlaying = isPlayingRef.current;
      console.log('Was playing before clip change:', wasPlaying);
      
      onClipChange(currentClipIndex + 1);
      
      // If it was playing, the new clip should start playing automatically
      // since we're not calling load() which would pause it
      if (wasPlaying) {
        console.log('Should autoplay since we skipped load()');
      }
    } else {
      // End of all clips
      console.log('All clips finished, stopping playback');
      setIsPlaying(false);
      isPlayingRef.current = false;
      setCurrentTime(0);
      onClipChange(0); // Reset to first clip
    }
  }, [currentClipIndex, sortedClips.length, onClipChange]);

  const handleError = useCallback((e: React.SyntheticEvent<HTMLVideoElement, Event>) => {
    console.error('Video error:', e);
    setError('Failed to load video clip');
    setIsLoading(false);
  }, []);

  // Playback controls
  const handlePlayPause = async () => {
    if (!videoRef.current) return;

    try {
      if (isPlaying) {
        console.log('Manual pause triggered');
        videoRef.current.pause();
        isPlayingRef.current = false;
      } else {
        console.log('Manual play triggered');
        await videoRef.current.play();
        isPlayingRef.current = true;
      }
    } catch (error) {
      console.error('Playback error:', error);
      setError('Playback failed');
    }
  };

  const handleSeek = (event: Event, newValue: number | number[]) => {
    if (!videoRef.current || !currentClip) return;
    
    const absoluteTime = newValue as number;
    
    // Find which clip this time corresponds to
    let accumulatedTime = 0;
    let targetClipIndex = 0;
    let clipTime = 0;
    
    for (let i = 0; i < sortedClips.length; i++) {
      if (absoluteTime <= accumulatedTime + sortedClips[i].duration) {
        targetClipIndex = i;
        clipTime = absoluteTime - accumulatedTime;
        break;
      }
      accumulatedTime += sortedClips[i].duration;
    }
    
    // Switch to target clip if needed
    if (targetClipIndex !== currentClipIndex) {
      onClipChange(targetClipIndex);
    }
    
    // Seek to the correct time in the full video
    setTimeout(() => {
      if (videoRef.current && clips[targetClipIndex]) {
        const targetClip = clips[targetClipIndex];
        const videoTime = targetClip.start_time + clipTime;
        videoRef.current.currentTime = videoTime;
        setCurrentTime(clipTime);
      }
    }, 100);
  };

  const handleVolumeToggle = () => {
    if (!videoRef.current) return;
    
    if (isMuted) {
      videoRef.current.volume = volume;
      setIsMuted(false);
    } else {
      videoRef.current.volume = 0;
      setIsMuted(true);
    }
  };

  const handleVolumeChange = (event: Event, newValue: number | number[]) => {
    const newVolume = newValue as number;
    setVolume(newVolume);
    
    if (videoRef.current) {
      videoRef.current.volume = newVolume;
      setIsMuted(newVolume === 0);
    }
  };

  // Update video element when playing state changes
  useEffect(() => {
    if (!videoRef.current) return;

    if (isPlaying) {
      videoRef.current.play().catch(console.error);
    } else {
      videoRef.current.pause();
    }
  }, [isPlaying]);

  // Update video element when clip changes
  useEffect(() => {
    if (!videoRef.current || !currentClip) return;
    
    // Seek to the start time of the current clip
    videoRef.current.currentTime = currentClip.start_time;
    setCurrentTime(0);
  }, [currentClipIndex, currentClip]);

  if (clips.length === 0) {
    return (
      <Box 
        className={className}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '200px',
          backgroundColor: '#f5f5f5',
          ...style,
        }}
      >
        <Typography variant="body2" color="text.secondary">
          No video clips available for preview
        </Typography>
      </Box>
    );
  }

  return (
    <Box className={className} style={style}>
      {/* Video Element */}
      <Box sx={{ position: 'relative', width: '100%', height: 'auto', backgroundColor: '#000' }}>
        <video
          ref={videoRef}
          style={{ width: '100%', height: 'auto', maxHeight: '400px' }}
          onLoadedMetadata={handleLoadedMetadata}
          onTimeUpdate={handleTimeUpdate}
          onEnded={handleEnded}
          onError={handleError}
          onLoadStart={() => setIsLoading(true)}
          onCanPlay={() => setIsLoading(false)}
          onPlay={() => {
            console.log('Video onPlay event triggered');
            setIsPlaying(true);
            isPlayingRef.current = true;
          }}
          onPause={() => {
            console.log('Video onPause event triggered - this might be from load()');
            // Don't update the ref here as it might be from load() causing a pause
            // Only update the state for UI purposes
            setIsPlaying(false);
          }}
        />
        
        {/* Loading Overlay */}
        {isLoading && (
          <Box
            sx={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: 'rgba(0, 0, 0, 0.7)',
              color: 'white',
            }}
          >
            <LinearProgress sx={{ width: '200px' }} />
          </Box>
        )}
        
        {/* Error Overlay */}
        {error && (
          <Box
            sx={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: 'rgba(0, 0, 0, 0.8)',
              color: 'white',
            }}
          >
            <Alert severity="error" sx={{ backgroundColor: 'transparent' }}>
              {error}
            </Alert>
          </Box>
        )}
      </Box>

      {/* Controls */}
      <Box sx={{ p: 2, backgroundColor: '#f5f5f5' }}>
        {/* Play/Pause and Volume Controls */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <IconButton onClick={handlePlayPause} sx={{ color: '#1976d2' }}>
            {isPlaying ? <PauseIcon /> : <PlayIcon />}
          </IconButton>
          
          <IconButton onClick={handleVolumeToggle} sx={{ color: '#1976d2' }}>
            {isMuted ? <VolumeOffIcon /> : <VolumeUpIcon />}
          </IconButton>
          
          <Slider
            value={isMuted ? 0 : volume}
            onChange={handleVolumeChange}
            min={0}
            max={1}
            step={0.1}
            sx={{ 
              width: 80,
              color: '#1976d2',
              '& .MuiSlider-thumb': {
                backgroundColor: '#1976d2',
              },
              '& .MuiSlider-track': {
                backgroundColor: '#1976d2',
              },
              '& .MuiSlider-rail': {
                backgroundColor: 'rgba(25, 118, 210, 0.3)',
              },
            }}
          />
        </Box>

        {/* Progress Bar */}
        <Box sx={{ mb: 2, position: 'relative' }}>
          <Slider
            value={getAbsoluteTime()}
            onChange={handleSeek}
            min={0}
            max={totalDuration}
            step={0.1}
            sx={{ 
              width: '100%',
              color: '#1976d2',
              '& .MuiSlider-thumb': {
                backgroundColor: '#1976d2',
              },
              '& .MuiSlider-track': {
                backgroundColor: '#1976d2',
              },
              '& .MuiSlider-rail': {
                backgroundColor: 'rgba(25, 118, 210, 0.3)',
              },
            }}
          />
          
          {/* Clip boundary markers */}
          <Box sx={{ position: 'absolute', top: '50%', left: 0, right: 0, height: 0, pointerEvents: 'none' }}>
            {sortedClips.map((_, index) => {
              if (index === 0) return null; // Skip first clip (starts at 0)
              const clipStartTime = sortedClips.slice(0, index).reduce((sum, clip) => sum + clip.duration, 0);
              const percentage = (clipStartTime / totalDuration) * 100;
              return (
                <Box
                  key={index}
                  sx={{
                    position: 'absolute',
                    left: `${percentage}%`,
                    top: '-6px',
                    width: '2px',
                    height: '12px',
                    backgroundColor: '#ff6b35',
                    borderRadius: '1px',
                  }}
                />
              );
            })}
          </Box>
        </Box>

        {/* Time Display */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="caption" sx={{ color: '#000', fontWeight: 500 }}>
            {Math.floor(getAbsoluteTime() / 60)}:{(getAbsoluteTime() % 60).toFixed(1).padStart(4, '0')}
            {' / '}
            {Math.floor(totalDuration / 60)}:{(totalDuration % 60).toFixed(1).padStart(4, '0')}
          </Typography>
          
          <Typography variant="caption" sx={{ color: '#666' }}>
            Clip {currentClipIndex + 1} of {sortedClips.length}
          </Typography>
        </Box>
      </Box>
    </Box>
  );
};
