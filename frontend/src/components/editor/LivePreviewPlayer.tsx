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
  const primaryVideoRef = useRef<HTMLVideoElement>(null);
  // Legacy refs/states no longer used with HLS-based player
  const isPlayingRef = useRef(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const currentTimeRef = useRef(0);
  const lastUpdateTimeRef = useRef(0);
  const seekTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isTransitioningRef = useRef(false);
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

  // Load current clip - Single video approach
  useEffect(() => {
    if (!currentClip) return;

    const primaryVideo = primaryVideoRef.current;
    if (!primaryVideo) return;

    console.log('LOADING EFFECT: currentClipIndex=', currentClipIndex);
    console.log('  → Current video src:', primaryVideo.src);
    console.log('  → Target clip src:', currentClip.stream_url);

    // Compare URLs - video.src is absolute, clip URL might be relative
    const videoPath = primaryVideo.src ? new URL(primaryVideo.src).pathname : '';
    const clipPath = currentClip.stream_url.startsWith('http')
      ? new URL(currentClip.stream_url).pathname
      : currentClip.stream_url;
    const urlsMatch = videoPath === clipPath;

    console.log('  → URLs match:', urlsMatch, 'readyState:', primaryVideo.readyState);

    // If video already has the correct clip loaded and ready, don't reload
    if (urlsMatch && primaryVideo.readyState >= 2) {
      console.log('  → SKIP: Video already has correct clip loaded');
      setIsLoading(false);
      return;
    }

    console.log('  → LOADING clip into video');
    setIsLoading(true);
    setError(null);

    // Load current clip
    primaryVideo.src = currentClip.stream_url;
    primaryVideo.load();

    // Set currentTime when loaded
    const handleLoadedData = () => {
      if (primaryVideo.readyState >= 2) {
        primaryVideo.currentTime = 0;
        setIsLoading(false);
        console.log('  → Video loaded and seeked to 0.0');
      }
    };
    primaryVideo.addEventListener('loadeddata', handleLoadedData, { once: true });

    // Reset time when switching clips
    currentTimeRef.current = 0;
    setCurrentTime(0);

    return () => {
      primaryVideo.removeEventListener('loadeddata', handleLoadedData);
    };

  }, [currentClip, currentClipIndex]);

  // Handle video events
  const handleLoadedMetadata = useCallback(() => {
    const primaryVideo = primaryVideoRef.current;
    if (primaryVideo) {
      setDuration(primaryVideo.duration);
      setIsLoading(false);
    }
  }, []);

  // Function to advance to next clip - Single video approach
  const advanceToNextClip = useCallback(() => {
    // Prevent double transitions
    if (isTransitioningRef.current) {
      console.log('BLOCKED - already transitioning');
      return;
    }

    console.log('ADVANCING from clip', currentClipIndex, 'to', currentClipIndex + 1);

    if (currentClipIndex < sortedClips.length - 1) {
      const wasPlaying = isPlayingRef.current;
      isTransitioningRef.current = true;

      const primaryVideo = primaryVideoRef.current;
      const nextClip = sortedClips[currentClipIndex + 1];

      if (primaryVideo && nextClip) {
        // Pause current playback
        primaryVideo.pause();

        // Load next clip
        console.log('Loading next clip:', nextClip.stream_url);
        primaryVideo.src = nextClip.stream_url;
        primaryVideo.currentTime = 0;
        primaryVideo.load();

        // Update clip index
        onClipChange(currentClipIndex + 1);

        // Reset time
        currentTimeRef.current = 0;
        setCurrentTime(0);

        // Maintain playing state - play() will be called by useEffect
        if (wasPlaying) {
          setIsPlaying(true);
          isPlayingRef.current = true;
        }
      }

      // Clear transition flag
      setTimeout(() => {
        isTransitioningRef.current = false;
      }, 100);
    } else {
      // End of all clips
      setIsPlaying(false);
      isPlayingRef.current = false;
      currentTimeRef.current = 0;
      setCurrentTime(0);
      onClipChange(0);
      isTransitioningRef.current = false;
    }
  }, [currentClipIndex, sortedClips, onClipChange]);

  const handleTimeUpdate = useCallback(() => {
    const primaryVideo = primaryVideoRef.current;
    if (primaryVideo && currentClip) {
      const videoTime = primaryVideo.currentTime;

      // Check if we've reached the end of the current clip file
      if (videoTime >= currentClip.duration) {
        // Don't process if we're already transitioning
        if (isTransitioningRef.current) {
          return;
        }

        console.log('END REACHED clip', currentClipIndex, 'time:', videoTime, 'duration:', currentClip.duration);
        // Pause the video to prevent it from continuing
        primaryVideo.pause();
        // Advance to next clip
        advanceToNextClip();
        return;
      }

      // Calculate time within the current clip (same as videoTime since clips start at 0)
      const clipTime = Math.max(0, videoTime);

      // Throttle updates to prevent infinite loops (only update every 500ms)
      const now = Date.now();
      if (now - lastUpdateTimeRef.current >= 500 && Math.abs(currentTimeRef.current - clipTime) >= 0.5) {
        currentTimeRef.current = clipTime;
        setCurrentTime(clipTime);
        lastUpdateTimeRef.current = now;
      }

      // Calculate absolute time across all clips
      let absoluteTime = 0;
      for (let i = 0; i < currentClipIndex; i++) {
        absoluteTime += clips[i].duration;
      }
      absoluteTime += clipTime;

      onTimeUpdate(absoluteTime, currentClipIndex);
    }
  }, [currentClipIndex, clips, currentClip, onTimeUpdate, advanceToNextClip]);

  const handleError = useCallback((e: React.SyntheticEvent<HTMLVideoElement, Event>) => {
    console.error('Video error:', e);
    setError('Failed to load video clip');
    setIsLoading(false);
  }, []);

  // Playback controls
  const handlePlayPause = async () => {
    const primaryVideo = primaryVideoRef.current;
    if (!primaryVideo) return;

    try {
      if (isPlaying) {
        primaryVideo.pause();
        setIsPlaying(false);
        isPlayingRef.current = false;
      } else {
        setIsPlaying(true);
        isPlayingRef.current = true;
        // The useEffect will handle the actual playing
      }
    } catch (err: unknown) {
      const e = err as { name?: string };
      // Don't log AbortError as it's expected during transitions
      if (e?.name !== 'AbortError') {
        console.error('Playback error:', err);
        setError('Playback failed');
      }
    }
  };

  const handleSeek = (event: Event, newValue: number | number[]) => {
    const primaryVideo = primaryVideoRef.current;
    if (!primaryVideo || !currentClip) return;

    // Clear any existing seek timeout to debounce rapid seeking
    if (seekTimeoutRef.current) {
      clearTimeout(seekTimeoutRef.current);
    }

    const absoluteTime = newValue as number;

    // Debounce seek operations to prevent rapid requests
    seekTimeoutRef.current = setTimeout(() => {
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

      // Seek to the correct time in the clip file (which starts at 0)
      setTimeout(() => {
        if (primaryVideo && clips[targetClipIndex]) {
          // Clip files start at 0, so just seek to clipTime directly
          primaryVideo.currentTime = clipTime;
          currentTimeRef.current = clipTime;
          setCurrentTime(clipTime);
        }
      }, 50);
    }, 150); // Debounce for 150ms
  };

  const handleVolumeToggle = () => {
    const primaryVideo = primaryVideoRef.current;
    if (!primaryVideo) return;

    if (isMuted) {
      primaryVideo.volume = volume;
      setIsMuted(false);
    } else {
      primaryVideo.volume = 0;
      setIsMuted(true);
    }
  };

  const handleVolumeChange = (event: Event, newValue: number | number[]) => {
    const primaryVideo = primaryVideoRef.current;
    if (!primaryVideo) return;

    const newVolume = (newValue as number) / 100;
    primaryVideo.volume = newVolume;
    setVolume(newVolume);
    setIsMuted(newVolume === 0);
  };

  // Update video element when playing state changes
  useEffect(() => {
    const primaryVideo = primaryVideoRef.current;
    if (!primaryVideo) return;

    console.log('PLAY EFFECT: isPlaying=', isPlaying, 'readyState=', primaryVideo.readyState, 'paused=', primaryVideo.paused, 'currentTime=', primaryVideo.currentTime);
    console.log('  → currentClipIndex:', currentClipIndex, 'currentClip src:', currentClip?.stream_url?.substring(currentClip.stream_url.lastIndexOf('/') + 1));

    if (isPlaying) {
      // Try to play immediately if ready
      if (primaryVideo.readyState >= 2 && primaryVideo.paused) {
        console.log('→ Playing video now - currentTime:', primaryVideo.currentTime, 'duration:', primaryVideo.duration);
        const playPromise = primaryVideo.play();
        const playStartTime = performance.now();
        playPromise
          .then(() => {
            const playDuration = performance.now() - playStartTime;
            console.log('✓ Play succeeded in', playDuration.toFixed(2), 'ms');
            // Check if video is actually progressing
            setTimeout(() => {
              console.log('  Video 50ms later: currentTime=', primaryVideo.currentTime, 'paused=', primaryVideo.paused);
            }, 50);
          })
          .catch((err: unknown) => {
            const e = err as { name?: string };
            if (e?.name !== 'AbortError') {
              console.error('Play error:', err);
            } else {
              console.log('Play aborted');
            }
          });
      } else if (primaryVideo.readyState < 2) {
        // Video not ready yet, wait for it to load
        console.log('→ Waiting for canplay');
        const handleCanPlay = () => {
          if (primaryVideo.paused && isPlayingRef.current) {
            console.log('→ canplay fired, playing now');
            primaryVideo.play()
              .then(() => {
                console.log('✓ Play succeeded after canplay');
              })
              .catch((err: unknown) => {
                const e = err as { name?: string };
                if (e?.name !== 'AbortError') {
                  console.error('Delayed play error:', err);
                } else {
                  console.log('Delayed play aborted');
                }
              });
          }
          primaryVideo.removeEventListener('canplay', handleCanPlay);
        };
        primaryVideo.addEventListener('canplay', handleCanPlay);

        // Cleanup function
        return () => {
          primaryVideo.removeEventListener('canplay', handleCanPlay);
        };
      } else {
        console.log('→ Video already playing');
      }
    } else {
      console.log('→ Pausing video');
      primaryVideo.pause();
    }
  }, [isPlaying, currentClipIndex, currentClip]);


  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (seekTimeoutRef.current) {
        clearTimeout(seekTimeoutRef.current);
      }
    };
  }, []);

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
      {/* Single Video Element - Much simpler and more reliable */}
      <Box sx={{ position: 'relative', width: '100%', paddingTop: '56.25%', backgroundColor: '#000' }}>
        <video
          ref={primaryVideoRef}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            transform: 'translateZ(0)',
          }}
          onLoadedMetadata={handleLoadedMetadata}
          onTimeUpdate={handleTimeUpdate}
          onError={handleError}
          onLoadStart={() => setIsLoading(true)}
          onCanPlay={() => setIsLoading(false)}
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
