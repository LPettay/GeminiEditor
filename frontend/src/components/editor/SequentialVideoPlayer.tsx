/**
 * Sequential Video Player - Plays multiple clips as if they were one video
 */

import { useRef, useState, useEffect } from 'react';
import Hls from 'hls.js';
import { Box, IconButton, Slider, Typography, Paper, LinearProgress } from '@mui/material';
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
  hlsManifestUrl?: string; // Optional unified EDL manifest override
}

export default function SequentialVideoPlayer({
  clips,
  onTimeUpdate,
  onClipChange,
  projectId,
  editId,
  hlsManifestUrl,
}: SequentialVideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const preloadVideoRef = useRef<HTMLVideoElement>(null);
  const hlsRef = useRef<Hls | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const prefetchedNextRef = useRef<string | null>(null);
  
  const [currentClipIndex, setCurrentClipIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [bufferReady, setBufferReady] = useState(false);
  
  const preloadCacheRef = useRef<Map<number, HTMLVideoElement>>(new Map());

  const totalDuration = clips.reduce((sum, clip) => sum + clip.duration, 0);

  // Calculate accumulated time up to current clip
  const getAccumulatedTime = (clipIndex: number) => clips.slice(0, clipIndex).reduce((sum, c) => sum + c.duration, 0);

  // For HLS playlist, video.currentTime is already global timeline time

  const usingUnifiedHls = Boolean(hlsManifestUrl);
  const isHlsMode = usingUnifiedHls;
  
  // Preload buffer: Load 3 clips ahead before allowing playback
  useEffect(() => {
    if (isHlsMode || clips.length === 0) {
      setBufferReady(true);
      return;
    }
    
    console.log('[BUFFER] Preloading first 3 clips...');
    const BUFFER_SIZE = 3;
    const clipsToPreload = Math.min(BUFFER_SIZE, clips.length);
    let loadedCount = 0;
    
    const preloadClip = (index: number) => {
      if (index >= clips.length) return;
      
      const video = document.createElement('video');
      video.preload = 'auto';
      video.src = clips[index].clip_url;
      
      const onCanPlay = () => {
        console.log(`[BUFFER] Clip ${index} ready (${video.readyState})`);
        preloadCacheRef.current.set(index, video);
        loadedCount++;
        
        if (loadedCount >= clipsToPreload) {
          console.log(`[BUFFER] ✓ Buffer ready! ${loadedCount} clips preloaded`);
          setBufferReady(true);
        }
      };
      
      video.addEventListener('canplaythrough', onCanPlay, { once: true });
      video.load();
    };
    
    for (let i = 0; i < clipsToPreload; i++) {
      preloadClip(i);
    }
    
    // Cleanup
    return () => {
      preloadCacheRef.current.forEach(v => v.src = '');
      preloadCacheRef.current.clear();
    };
  }, [clips, isHlsMode]);

  // Initialize HLS once when unified manifest is available
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !hlsManifestUrl) return;

    // Cleanup existing instance
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }

    if (Hls.isSupported()) {
      const hls = new Hls({
        autoStartLoad: true,
        lowLatencyMode: false,
        backBufferLength: 2,
        maxBufferLength: 18,
        maxMaxBufferLength: 24,
        maxBufferHole: 0.1,
      });
      hlsRef.current = hls;
      hls.attachMedia(video);
      hls.on(Hls.Events.MEDIA_ATTACHED, () => {
        console.log('[HLS] Loading unified manifest:', hlsManifestUrl);
        hls.loadSource(hlsManifestUrl);
      });
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        console.log('[HLS] Manifest parsed, duration:', video.duration);
      });
      hls.on(Hls.Events.FRAG_LOADED, (_, data) => {
        console.log('[HLS] Fragment loaded:', data.frag.sn, 'time:', data.frag.start.toFixed(2), 'dur:', data.frag.duration.toFixed(2));
      });
      hls.on(Hls.Events.BUFFER_APPENDED, () => {
        if (video.buffered.length > 0) {
          console.log('[HLS] Buffer:', video.buffered.start(0).toFixed(2), '-', video.buffered.end(0).toFixed(2), 'readyState:', video.readyState);
        }
      });
      hls.on(Hls.Events.ERROR, (_, data) => {
        if (data.fatal) {
          console.error('[HLS] Fatal error:', data);
        } else {
          console.warn('[HLS] Recoverable error:', data.details);
        }
      });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari native HLS
      console.log('[HLS] Safari native mode:', hlsManifestUrl);
      video.src = hlsManifestUrl;
    }

    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
  }, [hlsManifestUrl]);

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
      
      // Maintain rolling buffer: preload 3 clips ahead
      const BUFFER_SIZE = 3;
      const currentClip = clips[currentClipIndex];
      if (currentClip && time >= currentClip.duration * 0.5) {
        // When halfway through current clip, ensure next 3 are buffered
        for (let offset = 1; offset <= BUFFER_SIZE; offset++) {
          const targetIndex = currentClipIndex + offset;
          if (targetIndex < clips.length && !preloadCacheRef.current.has(targetIndex)) {
            const video = document.createElement('video');
            video.preload = 'auto';
            video.src = clips[targetIndex].clip_url;
            video.addEventListener('canplaythrough', () => {
              console.log(`[BUFFER] Clip ${targetIndex} ready`);
              preloadCacheRef.current.set(targetIndex, video);
            }, { once: true });
            video.load();
          }
        }
        
        // Clean up old clips (more than 2 behind current)
        preloadCacheRef.current.forEach((video, index) => {
          if (index < currentClipIndex - 2) {
            video.src = '';
            preloadCacheRef.current.delete(index);
            console.log(`[BUFFER] Cleaned up clip ${index}`);
          }
        });
      }
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
    if (!video || !bufferReady) {
      console.log('[PLAY] Buffer not ready yet, please wait...');
      return;
    }
    console.log('[PLAY] Toggle called, isPlaying:', isPlaying, 'readyState:', video.readyState, 'paused:', video.paused);
    if (isPlaying) {
      video.pause();
      setIsPlaying(false);
    } else {
      console.log('[PLAY] Attempting play...');
      video.play()
        .then(() => {
          console.log('[PLAY] Play successful');
          setIsPlaying(true);
        })
        .catch((err) => {
          console.error('[PLAY] Play failed:', err);
        });
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
      {/* Loading Overlay */}
      {!bufferReady && !isHlsMode && (
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: 'rgba(0, 0, 0, 0.8)',
            zIndex: 10,
          }}
        >
          <LinearProgress sx={{ width: '50%', mb: 2 }} />
          <Typography color="white">Buffering clips...</Typography>
        </Box>
      )}
      
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
      
      {/* Hidden preload video for next clip */}
      <video
        ref={preloadVideoRef}
        style={{ display: 'none' }}
        preload="auto"
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

