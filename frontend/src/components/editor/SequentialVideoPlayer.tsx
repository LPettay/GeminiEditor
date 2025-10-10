/**
 * Sequential Video Player - Plays multiple clips as if they were one video
 */

import { useRef, useState, useEffect } from 'react';
import { Box, IconButton, Slider, Typography, Paper } from '@mui/material';
import {
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  VolumeUp as VolumeIcon,
  VolumeOff as VolumeMuteIcon,
  Fullscreen as FullscreenIcon,
} from '@mui/icons-material';
import { ClipPreview } from '../../api/client';

interface SequentialVideoPlayerProps {
  clips: ClipPreview[];
  onTimeUpdate?: (currentTime: number, clipIndex: number) => void;
  onClipChange?: (clipIndex: number) => void;
}

export default function SequentialVideoPlayer({
  clips,
  onTimeUpdate,
  onClipChange,
}: SequentialVideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  
  const [currentClipIndex, setCurrentClipIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const currentClip = clips[currentClipIndex];
  const totalDuration = clips.reduce((sum, clip) => sum + clip.duration, 0);

  // Calculate accumulated time up to current clip
  const getAccumulatedTime = (clipIndex: number) => {
    return clips.slice(0, clipIndex).reduce((sum, clip) => sum + clip.duration, 0);
  };

  // Get global time (across all clips)
  const globalTime = getAccumulatedTime(currentClipIndex) + currentTime;

  // Load clip when index changes
  useEffect(() => {
    if (videoRef.current && currentClip) {
      const video = videoRef.current;
      video.src = currentClip.clip_url;
      video.currentTime = 0;
      
      if (isPlaying) {
        video.play().catch(console.error);
      }
      
      onClipChange?.(currentClipIndex);
    }
  }, [currentClipIndex, currentClip]);

  // Handle video end - move to next clip
  const handleVideoEnd = () => {
    if (currentClipIndex < clips.length - 1) {
      setCurrentClipIndex(prev => prev + 1);
      setCurrentTime(0);
    } else {
      // End of all clips
      setIsPlaying(false);
      setCurrentClipIndex(0);
      setCurrentTime(0);
    }
  };

  // Handle time update
  const handleTimeUpdate = () => {
    if (videoRef.current) {
      const time = videoRef.current.currentTime;
      setCurrentTime(time);
      onTimeUpdate?.(globalTime, currentClipIndex);
    }
  };

  // Handle duration change
  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration);
    }
  };

  // Play/Pause
  const togglePlayPause = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play().catch(console.error);
      }
      setIsPlaying(!isPlaying);
    }
  };

  // Seek to global time
  const handleSeek = (newGlobalTime: number) => {
    let accumulatedTime = 0;
    let targetClipIndex = 0;
    
    // Find which clip contains this time
    for (let i = 0; i < clips.length; i++) {
      if (newGlobalTime < accumulatedTime + clips[i].duration) {
        targetClipIndex = i;
        break;
      }
      accumulatedTime += clips[i].duration;
    }
    
    const localTime = newGlobalTime - accumulatedTime;
    
    if (targetClipIndex !== currentClipIndex) {
      setCurrentClipIndex(targetClipIndex);
      // Will load new clip, then seek
      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.currentTime = localTime;
        }
      }, 100);
    } else {
      if (videoRef.current) {
        videoRef.current.currentTime = localTime;
      }
    }
  };

  // Volume control
  const handleVolumeChange = (newVolume: number) => {
    setVolume(newVolume);
    if (videoRef.current) {
      videoRef.current.volume = newVolume;
    }
    if (newVolume === 0) {
      setIsMuted(true);
    } else if (isMuted) {
      setIsMuted(false);
    }
  };

  // Mute toggle
  const toggleMute = () => {
    if (videoRef.current) {
      videoRef.current.muted = !isMuted;
      setIsMuted(!isMuted);
    }
  };

  // Fullscreen toggle
  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen().catch(console.error);
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  // Format time as MM:SS
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  if (clips.length === 0) {
    return (
      <Paper sx={{ p: 4, textAlign: 'center' }}>
        <Typography color="text.secondary">No clips to preview</Typography>
      </Paper>
    );
  }

  return (
    <Paper ref={containerRef} sx={{ bgcolor: 'black', position: 'relative' }}>
      {/* Video Element */}
      <video
        ref={videoRef}
        style={{
          width: '100%',
          height: 'auto',
          display: 'block',
        }}
        onEnded={handleVideoEnd}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onClick={togglePlayPause}
      />

      {/* Controls Overlay */}
      <Box
        sx={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          background: 'linear-gradient(transparent, rgba(0,0,0,0.8))',
          p: 2,
        }}
      >
        {/* Progress Bar */}
        <Slider
          value={globalTime}
          min={0}
          max={totalDuration}
          onChange={(_, value) => handleSeek(value as number)}
          sx={{
            mb: 1,
            '& .MuiSlider-thumb': {
              width: 16,
              height: 16,
            },
          }}
        />

        {/* Control Buttons */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {/* Play/Pause */}
          <IconButton onClick={togglePlayPause} sx={{ color: 'white' }}>
            {isPlaying ? <PauseIcon /> : <PlayIcon />}
          </IconButton>

          {/* Time Display */}
          <Typography variant="body2" sx={{ color: 'white', minWidth: 100 }}>
            {formatTime(globalTime)} / {formatTime(totalDuration)}
          </Typography>

          {/* Clip Indicator */}
          <Typography variant="caption" sx={{ color: 'white', opacity: 0.7 }}>
            Clip {currentClipIndex + 1}/{clips.length}
          </Typography>

          <Box sx={{ flexGrow: 1 }} />

          {/* Volume Control */}
          <IconButton onClick={toggleMute} sx={{ color: 'white' }}>
            {isMuted || volume === 0 ? <VolumeMuteIcon /> : <VolumeIcon />}
          </IconButton>
          <Slider
            value={isMuted ? 0 : volume}
            min={0}
            max={1}
            step={0.1}
            onChange={(_, value) => handleVolumeChange(value as number)}
            sx={{ width: 100, color: 'white' }}
          />

          {/* Fullscreen */}
          <IconButton onClick={toggleFullscreen} sx={{ color: 'white' }}>
            <FullscreenIcon />
          </IconButton>
        </Box>
      </Box>
    </Paper>
  );
}

