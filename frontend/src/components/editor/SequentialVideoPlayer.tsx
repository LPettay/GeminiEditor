/**
 * Sequential Video Player - Plays multiple clips as if they were one video
 */

import React, { useRef, useState, useEffect } from 'react';
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

const SequentialVideoPlayer = React.memo(function SequentialVideoPlayer({
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
  const [firstClipReady, setFirstClipReady] = useState(false);
  const [isSeeking, setIsSeeking] = useState(false);
  const [isLoadingClip, setIsLoadingClip] = useState(false);
  
  const preloadCacheRef = useRef<Map<number, HTMLVideoElement>>(new Map());
  const intendedPlayingRef = useRef(false); // Track if user intends video to be playing
  const [isPrimaryActive, setIsPrimaryActive] = useState(true); // Toggle between primary and preload video
  const lastLoadedClipRef = useRef<number>(-1); // Prevent duplicate loads

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
      setFirstClipReady(true);
      return;
    }
    
    setFirstClipReady(false); // Reset first clip ready state
    const clipsToPreload = clips.length; // PRELOAD ALL CLIPS
    let loadedCount = 0;
    
    console.log(`[BUFFER] Preloading ALL ${clipsToPreload} clips...`);
    
    const preloadClip = (index: number) => {
      if (index >= clips.length) return;
      
      const video = document.createElement('video');
      video.preload = 'auto';
      video.src = clips[index].clip_url;
      
      const onCanPlay = () => {
        preloadCacheRef.current.set(index, video);
        loadedCount++;
        
        // First clip is ready immediately
        if (index === 0) {
          setFirstClipReady(true);
          console.log('[BUFFER] First clip ready');
        }
        
        if (loadedCount >= clipsToPreload) {
          setBufferReady(true);
          console.log(`[BUFFER] All ${loadedCount} clips preloaded!`);
        } else if (loadedCount % 20 === 0) {
          console.log(`[BUFFER] ${loadedCount}/${clipsToPreload} clips loaded`);
        }
      };
      
      const onError = (e: any) => {
        // Silent - cleanup errors are expected
      };
      
      video.addEventListener('canplaythrough', onCanPlay, { once: true });
      video.addEventListener('error', onError, { once: true });
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
  }, [clips.length, isHlsMode]);

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
    const primaryVideo = videoRef.current;
    const preloadVideo = preloadVideoRef.current;
    if (!primaryVideo || !preloadVideo || isHlsMode) return;
    const current = clips[currentClipIndex];
    if (!current) return;
    
    // Prevent duplicate loads
    if (lastLoadedClipRef.current === currentClipIndex) {
      console.log(`[VIDEO] Clip ${currentClipIndex} already loaded, skipping`);
      return;
    }
    
    console.log(`[VIDEO] Loading clip ${currentClipIndex}:`, current.clip_url);
    
    // Get the active and inactive video elements
    const activeVideo = isPrimaryActive ? primaryVideo : preloadVideo;
    const inactiveVideo = isPrimaryActive ? preloadVideo : primaryVideo;
    
    // Check if inactive video already has this clip loaded
    const inactivePath = inactiveVideo.src ? new URL(inactiveVideo.src, window.location.origin).pathname : '';
    const targetPath = current.clip_url.startsWith('http') ? new URL(current.clip_url).pathname : current.clip_url;
    
    if (inactivePath === targetPath) {
      // Instant switch to preloaded clip
      const shouldAutoPlay = intendedPlayingRef.current;
      lastLoadedClipRef.current = currentClipIndex;
      
      // Swap active video
      setIsPrimaryActive(!isPrimaryActive);
      
      // Play if needed
      if (shouldAutoPlay) {
        inactiveVideo.currentTime = 0;
        inactiveVideo.play().then(() => setIsPlaying(true));
        
        // Preload next clip
        const nextIndex = currentClipIndex + 1;
        if (nextIndex < clips.length) {
          activeVideo.src = clips[nextIndex].clip_url;
          activeVideo.currentTime = 0;
          activeVideo.load();
        }
      }
      
      onClipChange?.(currentClipIndex);
    } else {
      // Load into active video
      const activePath = activeVideo.src ? new URL(activeVideo.src, window.location.origin).pathname : '';
      if (activePath !== targetPath) {
        const shouldAutoPlay = intendedPlayingRef.current;
        lastLoadedClipRef.current = currentClipIndex;
        
        setIsLoadingClip(true);
        activeVideo.src = current.clip_url;
        activeVideo.load();
        
        const onCanPlay = () => {
          setIsLoadingClip(false);
          
          if (shouldAutoPlay) {
            activeVideo.play().then(() => setIsPlaying(true));
            
            // Preload next clip
            const nextIndex = currentClipIndex + 1;
            if (nextIndex < clips.length) {
              const inactiveVideo = isPrimaryActive ? preloadVideo : primaryVideo;
              inactiveVideo.src = clips[nextIndex].clip_url;
              inactiveVideo.currentTime = 0;
              inactiveVideo.load();
            }
          }
        };
        
        activeVideo.addEventListener('canplay', onCanPlay, { once: true });
        onClipChange?.(currentClipIndex);
      }
    }
  }, [isHlsMode, clips, currentClipIndex, isPrimaryActive]);

  // Handle video end
  const handleVideoEnd = () => {
    if (isHlsMode) {
      setIsPlaying(false);
      return;
    }
    if (currentClipIndex < clips.length - 1) {
      setCurrentClipIndex(prev => prev + 1);
      // Don't reset time - let handleTimeUpdate calculate the global time
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
    const localTime = video.currentTime;

    if (isHlsMode) {
      // HLS mode: time is already global
      setCurrentTime(localTime);
      // Map HLS absolute time into clip index using cumulative durations
      let acc = 0;
      let idx = 0;
      for (let i = 0; i < clips.length; i++) {
        if (localTime < acc + clips[i].duration) { idx = i; break; }
        acc += clips[i].duration;
      }
      if (idx !== currentClipIndex) {
        setCurrentClipIndex(idx);
        onClipChange?.(idx);
      }
      onTimeUpdate?.(localTime, idx);
    } else {
      // Sequential mode: convert local clip time to global timeline time
      const accumulatedTime = getAccumulatedTime(currentClipIndex);
      const globalTime = accumulatedTime + localTime;
      setCurrentTime(globalTime);
      onTimeUpdate?.(globalTime, currentClipIndex);
      
      // Maintain rolling buffer: preload 3 clips ahead
      const BUFFER_SIZE = 3;
      const currentClip = clips[currentClipIndex];
      if (currentClip && localTime >= currentClip.duration * 0.5) {
        // When halfway through current clip, ensure next 3 are buffered
        for (let offset = 1; offset <= BUFFER_SIZE; offset++) {
          const targetIndex = currentClipIndex + offset;
          if (targetIndex < clips.length && !preloadCacheRef.current.has(targetIndex)) {
            const video = document.createElement('video');
            video.preload = 'auto';
            video.src = clips[targetIndex].clip_url;
            video.addEventListener('canplaythrough', () => {
              preloadCacheRef.current.set(targetIndex, video);
            }, { once: true });
            video.load();
          }
        }
        
        // Clean up old clips (more than 2 behind current)
        preloadCacheRef.current.forEach((video, index) => {
          if (index < currentClipIndex - 2) {
            video.oncanplaythrough = null;
            video.onerror = null;
            video.src = '';
            preloadCacheRef.current.delete(index);
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
    const primaryVideo = videoRef.current;
    const preloadVideo = preloadVideoRef.current;
    const video = isPrimaryActive ? primaryVideo : preloadVideo;
    
    if (!video || !firstClipReady) return;
    
    if (isPlaying) {
      video.pause();
      setIsPlaying(false);
      intendedPlayingRef.current = false;
    } else {
      intendedPlayingRef.current = true;
      video.play().then(() => setIsPlaying(true));
    }
  };

  // Seek to global time
  const handleSeek = (newGlobalTime: number) => {
    const video = videoRef.current;
    if (!video) return;
    
    setIsSeeking(true);
    
    if (isHlsMode) {
      video.currentTime = newGlobalTime;
      setTimeout(() => setIsSeeking(false), 100);
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
      setTimeout(() => { 
        if (videoRef.current) { 
          videoRef.current.currentTime = localTime; 
        }
        setIsSeeking(false);
      }, 100);
    } else {
      video.currentTime = localTime;
      setTimeout(() => setIsSeeking(false), 50);
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
    <Paper ref={containerRef} sx={{ 
      bgcolor: 'black', 
      position: 'relative',
      minHeight: '400px',
      aspectRatio: '16/9',
      overflow: 'hidden'
    }}>
      {/* Loading Overlay */}
      {(!firstClipReady && !isHlsMode) && (
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
          <Typography color="white">Loading first clip...</Typography>
        </Box>
      )}
      
      {/* Seeking Overlay */}
      {isSeeking && (
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
            bgcolor: 'rgba(0, 0, 0, 0.3)',
            zIndex: 5,
          }}
        >
          <Typography color="white" variant="h6">Seeking...</Typography>
        </Box>
      )}
      
      {/* Loading Clip Overlay */}
      {isLoadingClip && (
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
            bgcolor: 'rgba(0, 0, 0, 0.9)',
            zIndex: 6,
          }}
        >
          <LinearProgress sx={{ width: '50%' }} />
        </Box>
      )}
      
      {/* Primary Video Element */}
      <video
        ref={videoRef}
        preload="auto"
        style={{
          width: '100%',
          height: '100%',
          display: isPrimaryActive ? 'block' : 'none',
          objectFit: 'contain',
          backgroundColor: 'black',
        }}
        onEnded={handleVideoEnd}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onClick={togglePlayPause}
      />
      
      {/* Preload/Secondary Video Element */}
      <video
        ref={preloadVideoRef}
        preload="auto"
        style={{
          width: '100%',
          height: '100%',
          display: isPrimaryActive ? 'none' : 'block',
          objectFit: 'contain',
          backgroundColor: 'black',
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
});

export default SequentialVideoPlayer;

