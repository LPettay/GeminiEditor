import { Box, Slider, Typography, Button, Stack } from '@mui/material';
import { useEffect, useRef, useState } from 'react';

// Format seconds -> HH:MM:SS
const fmt = (s: number) => {
  if (!Number.isFinite(s)) return '00:00:00';
  const d = new Date(Math.round(s) * 1000);
  return d.toISOString().substring(11, 19);
};

interface Props {
  videoUrl: string;
  onConfirm: (start: number, end: number) => void;
}

const VideoScrubber: React.FC<Props> = ({ videoUrl, onConfirm }) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [duration, setDuration] = useState(0);
  const [range, setRange] = useState<[number, number]>([0, 0]);
  const [currentTime, setCurrentTime] = useState(0);
  const [readyState, setReadyState] = useState(0);

  // Debug the video URL
  useEffect(() => {
    console.log('VideoScrubber: videoUrl =', videoUrl);
  }, [videoUrl]);

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
    };
    
    const onSeeked = () => {
      console.log('Seeked to:', v.currentTime);
    };
    
    const onError = (e: Event) => {
      console.error('Video error:', e);
      console.error('Video error details:', v.error);
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
  }, [videoUrl]);

  return (
    <Stack spacing={2} width="100%">
      <video 
        key={videoUrl} 
        ref={videoRef} 
        src={videoUrl} 
        controls 
        preload="metadata"
        style={{ width: '100%' }}
        crossOrigin="anonymous"
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
      </Box>
      
      {duration > 0 && (
        <>
          <Slider
            value={range}
            onChange={(_, val) => setRange(val as [number, number])}
            min={0}
            max={duration}
            step={0.1}
            valueLabelDisplay="auto"
            valueLabelFormat={(value) => fmt(value as number)}
          />
          <Box display="flex" justifyContent="space-between">
            <Typography variant="body2">In {fmt(range[0])}</Typography>
            <Typography variant="body2">Out {fmt(range[1])}</Typography>
          </Box>
          <Button variant="contained" onClick={() => onConfirm(range[0], range[1])}>
            Use These Points
          </Button>
        </>
      )}
    </Stack>
  );
};

export default VideoScrubber; 