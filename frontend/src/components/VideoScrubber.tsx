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

  // Load metadata
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onLoaded = () => {
      setDuration(v.duration);
      setRange([0, v.duration]);
    };
    v.addEventListener('loadedmetadata', onLoaded);
    return () => v.removeEventListener('loadedmetadata', onLoaded);
  }, [videoUrl]);

  return (
    <Stack spacing={2} width="100%">
      <video key={videoUrl} ref={videoRef} src={videoUrl} controls style={{ width: '100%' }} />
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