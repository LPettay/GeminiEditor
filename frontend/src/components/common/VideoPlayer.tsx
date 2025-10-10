/**
 * Video Player - Custom video player implementation using BaseVideoPlayer.
 * This can be easily swapped out with other implementations (e.g., Video.js, Plyr, etc.)
 */

import React, { useRef, useState, useEffect } from 'react';
import { Box, IconButton, Typography, Slider } from '@mui/material';
import {
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  VolumeUp as VolumeUpIcon,
  VolumeOff as VolumeOffIcon,
} from '@mui/icons-material';
import { BaseVideoPlayer, VideoPlayerRef } from './BaseVideoPlayer';

interface VideoPlayerProps {
  src: string;
  title?: string;
  onError?: (error: string) => void;
  className?: string;
  style?: React.CSSProperties;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({
  src,
  title,
  onError,
  className,
  style,
}) => {
  const videoRef = useRef<VideoPlayerRef>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const handlePlayPause = async () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        await videoRef.current.play();
      }
    }
  };

  const handleVolumeToggle = () => {
    if (videoRef.current) {
      if (isMuted) {
        videoRef.current.setVolume(volume);
        setIsMuted(false);
      } else {
        videoRef.current.setVolume(0);
        setIsMuted(true);
      }
    }
  };

  const handleVolumeChange = (event: Event, newValue: number | number[]) => {
    const newVolume = Array.isArray(newValue) ? newValue[0] : newValue;
    setVolume(newVolume);
    if (videoRef.current && !isMuted) {
      videoRef.current.setVolume(newVolume);
    }
  };

  const handleSeek = (event: Event, newValue: number | number[]) => {
    const newTime = Array.isArray(newValue) ? newValue[0] : newValue;
    if (videoRef.current) {
      videoRef.current.seek(newTime);
    }
  };

  const formatTime = (time: number) => {
    const minutes = Math.floor(time / 60);
    const seconds = Math.floor(time % 60);
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  };

  const handleError = (errorMessage: string) => {
    setError(errorMessage);
    setIsLoading(false);
    onError?.(errorMessage);
  };

  const handleLoadStart = () => {
    setIsLoading(true);
    setError(null);
  };

  const handleCanPlay = () => {
    setIsLoading(false);
  };

  // Reset state when src changes
  useEffect(() => {
    setCurrentTime(0);
    setDuration(0);
    setIsPlaying(false);
    setIsLoading(true);
    setError(null);
  }, [src]);

  return (
    <Box
      className={className}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        bgcolor: 'black',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        ...style,
      }}
    >
      <BaseVideoPlayer
        ref={videoRef}
        src={src}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onTimeUpdate={setCurrentTime}
        onLoadedMetadata={setDuration}
        onError={handleError}
        onLoadStart={handleLoadStart}
        onCanPlay={handleCanPlay}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
        }}
      />

      {/* Loading indicator */}
      {isLoading && !error && (
        <Box
          sx={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            color: 'white',
            textAlign: 'center',
          }}
        >
          <Typography variant="body2" color="white">
            Loading video...
          </Typography>
        </Box>
      )}

      {/* Error display */}
      {error && (
        <Box
          sx={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            color: 'white',
            textAlign: 'center',
            p: 3,
            bgcolor: 'rgba(0, 0, 0, 0.8)',
            borderRadius: 2,
          }}
        >
          <Typography variant="h6" color="error" gutterBottom>
            Video Error
          </Typography>
          <Typography variant="body2" sx={{ mb: 2 }}>
            {error}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            The video format may not be supported by your browser.
          </Typography>
        </Box>
      )}

      {/* Custom Video Controls */}
      <Box
        sx={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          bgcolor: 'rgba(0, 0, 0, 0.7)',
          p: 2,
          display: 'flex',
          alignItems: 'center',
          gap: 2,
        }}
      >
        <IconButton onClick={handlePlayPause} sx={{ color: 'white' }}>
          {isPlaying ? <PauseIcon /> : <PlayIcon />}
        </IconButton>

        <Typography variant="body2" sx={{ color: 'white', minWidth: 80 }}>
          {formatTime(currentTime)} / {formatTime(duration)}
        </Typography>

        <Box sx={{ flex: 1, mx: 2 }}>
          <Slider
            value={currentTime}
            min={0}
            max={duration || 0}
            onChange={handleSeek}
            sx={{
              color: 'white',
              '& .MuiSlider-thumb': {
                backgroundColor: 'white',
              },
              '& .MuiSlider-track': {
                backgroundColor: 'white',
              },
              '& .MuiSlider-rail': {
                backgroundColor: 'rgba(255, 255, 255, 0.3)',
              },
            }}
          />
        </Box>

        <IconButton onClick={handleVolumeToggle} sx={{ color: 'white' }}>
          {isMuted ? <VolumeOffIcon /> : <VolumeUpIcon />}
        </IconButton>

        <Box sx={{ width: 80 }}>
          <Slider
            value={isMuted ? 0 : volume}
            min={0}
            max={1}
            step={0.1}
            onChange={handleVolumeChange}
            sx={{
              color: 'white',
              '& .MuiSlider-thumb': {
                backgroundColor: 'white',
              },
              '& .MuiSlider-track': {
                backgroundColor: 'white',
              },
              '& .MuiSlider-rail': {
                backgroundColor: 'rgba(255, 255, 255, 0.3)',
              },
            }}
          />
        </Box>
      </Box>
    </Box>
  );
};
