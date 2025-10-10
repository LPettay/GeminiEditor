/**
 * Sequential Video Player - Plays multiple clips as if they were one video
 */

import { useRef, useState, useEffect } from 'react';
import Hls from 'hls.js';
import { Box, IconButton, Slider, Typography, Paper } from '@mui/material';
import {
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  VolumeUp as VolumeIcon,
  VolumeOff as VolumeMuteIcon,
  Fullscreen as FullscreenIcon,
} from '@mui/icons-material';
import { type ClipPreview } from '../../api/client';

interface SequentialVideoPlayerProps {
  clips: ClipPreview[];
  onTimeUpdate?: (currentTime: number, clipIndex: number) => void;
  onClipChange?: (clipIndex: number) => void;
  projectId?: string;
  editId?: string;
}

export default function SequentialVideoPlayer({
  clips,
  onTimeUpdate,
  onClipChange,
  projectId,
  editId,
}: SequentialVideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const hlsRef = useRef<Hls | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  
  const [currentClipIndex, setCurrentClipIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const totalDuration = clips.reduce((sum, clip) => sum + clip.duration, 0);

  // Calculate accumulated time up to current clip
  const getAccumulatedTime = (clipIndex: number) => clips.slice(0, clipIndex).reduce((sum, c) => sum + c.duration, 0);

  // For HLS playlist, video.currentTime is already global timeline time

  const isHlsMode = Boolean(projectId && editId);

  // Initialize HLS once and whenever project/edit changes or EDL order changes
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !isHlsMode) return;

    const playlistUrl = `/api/projects/${projectId}/edits/${editId}/playlist.m3u8?t=${Date.now()}`;

    // Cleanup existing instance
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }

    if (Hls.isSupported()) {
      const hls = new Hls({
        autoStartLoad: true,
        lowLatencyMode: false,
        backBufferLength: 0,
        maxBufferLength: 30,
      });
      hlsRef.current = hls;
      hls.attachMedia(video);
      hls.on(Hls.Events.MEDIA_ATTACHED, () => {
        hls.loadSource(playlistUrl);
      });
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (isPlaying) video.play().catch(() => {});
      });
      hls.on(Hls.Events.ERROR, (_, data) => {
        // Swallow recoverable errors; log fatal
        if (data.fatal) {
          console.error('hls.js fatal error', data);
        }
      });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari
      video.src = playlistUrl;
      video.addEventListener('loadedmetadata', () => {
        if (isPlaying) video.play().catch(() => {});
      }, { once: true });
    }

    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
  }, [isHlsMode, projectId, editId, clips.map(c => c.decision_id).join('|'), isPlaying]);

  // Fallback sequential mode: set src on clip/index change
  useEffect(() => {
    const video = videoRef.current;
    if (!video || isHlsMode) return;
    const current = clips[currentClipIndex];
    if (!current) return;
    // Only update if different
    const currentPath = video.src ? new URL(video.src, window.location.origin).pathname : '';
    const nextPath = current.clip_url.startsWith('http') ? new URL(current.clip_url).pathname : current.clip_url;
    if (currentPath !== nextPath) {
      video.src = current.clip_url;
      video.currentTime = 0;
      if (isPlaying) {
        video.play().catch(() => {});
      }
      onClipChange?.(currentClipIndex);
    }
  }, [isHlsMode, clips, currentClipIndex, isPlaying]);

  // Handle video end
  const handleVideoEnd = () => {
    if (isHlsMode) {
      setIsPlaying(false);
      return;
    }
    if (currentClipIndex < clips.length - 1) {
      setCurrentClipIndex(prev => prev + 1);
      setCurrentTime(0);
    } else {
      setIsPlaying(false);
      setCurrentClipIndex(0);
      setCurrentTime(0);
    }
  };

  // Handle time update
  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (!video) return;
    const time = video.currentTime;
    setCurrentTime(time);

    if (isHlsMode) {
      // Map HLS absolute time into clip index using cumulative durations
      let acc = 0;
      let idx = 0;
      for (let i = 0; i < clips.length; i++) {
        if (time < acc + clips[i].duration) { idx = i; break; }
        acc += clips[i].duration;
      }
      if (idx !== currentClipIndex) {
        setCurrentClipIndex(idx);
        onClipChange?.(idx);
      }
      onTimeUpdate?.(time, idx);
    } else {
      const acc = getAccumulatedTime(currentClipIndex);
      onTimeUpdate?.(acc + time, currentClipIndex);
    }
  };

  // Handle duration change
  const handleLoadedMetadata = () => {
    const video = videoRef.current;
    if (!video) return;
    // duration corresponds to full playlist duration
    setDuration(video.duration || totalDuration);
  };

  // Play/Pause
  const togglePlayPause = () => {
    const video = videoRef.current;
    if (!video) return;
    if (isPlaying) {
      video.pause();
      setIsPlaying(false);
    } else {
      video.play().then(() => setIsPlaying(true)).catch(() => {});
    }
  };

  // Seek to global time
  const handleSeek = (newGlobalTime: number) => {
    const video = videoRef.current;
    if (!video) return;
    if (isHlsMode) {
      video.currentTime = newGlobalTime;
      return;
    }
    let accumulatedTime = 0;
    let targetClipIndex = 0;
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
      setTimeout(() => { if (videoRef.current) { videoRef.current.currentTime = localTime; } }, 100);
    } else {
      video.currentTime = localTime;
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
          value={currentTime}
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
            {formatTime(currentTime)} / {formatTime(totalDuration)}
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

