import { useEffect, useRef, useState } from 'react';
import { Box, IconButton, LinearProgress } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';

interface Props {
  url: string;
}

/**
 * A lightweight audio preview component that replaces the earlier waveform visualization.
 * It renders a hidden HTMLAudioElement and exposes play/pause controls along with
 * a simple progress bar.
 */
const AudioPreview: React.FC<Props> = ({ url }) => {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0); // 0–100 percentage
  const [isReady, setIsReady] = useState(false);

  const togglePlay = () => {
    const audio = audioRef.current;
    if (!audio || !isReady) return;
    if (audio.paused) {
      audio.play();
    } else {
      audio.pause();
    }
  };

  // Attach listeners once
  useEffect(() => {
    console.log('AudioPreview: Creating audio element for URL:', url);
    const audio = new Audio(url);
    audioRef.current = audio;

    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onCanPlay = () => {
      console.log('AudioPreview: Audio can play, enabling button');
      setIsReady(true);
    };
    const onError = (e: Event) => {
      console.error('AudioPreview: Audio loading error:', e);
      console.error('AudioPreview: Error details:', audio.error);
    };
    const onLoadStart = () => console.log('AudioPreview: Loading started');
    const onLoadedData = () => console.log('AudioPreview: Data loaded');
    const onTimeUpdate = () => {
      if (!audio.duration) return;
      setProgress((audio.currentTime / audio.duration) * 100);
    };
    const onEnded = () => {
      setIsPlaying(false);
      setProgress(0);
    };

    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);
    audio.addEventListener('canplay', onCanPlay);
    audio.addEventListener('error', onError);
    audio.addEventListener('loadstart', onLoadStart);
    audio.addEventListener('loadeddata', onLoadedData);
    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('ended', onEnded);

    return () => {
      audio.pause();
      audio.src = '';
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
      audio.removeEventListener('canplay', onCanPlay);
      audio.removeEventListener('error', onError);
      audio.removeEventListener('loadstart', onLoadStart);
      audio.removeEventListener('loadeddata', onLoadedData);
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('ended', onEnded);
    };
  }, [url]);

  return (
    <Box display="flex" alignItems="center" width="100%">
      <IconButton onClick={togglePlay} size="small" sx={{ mr: 1 }} disabled={!isReady}>
        {isPlaying ? <PauseIcon /> : <PlayArrowIcon />}
      </IconButton>
      <Box sx={{ flexGrow: 1 }}>
        <LinearProgress 
          variant={isReady ? "determinate" : "indeterminate"} 
          value={progress} 
          sx={{ height: 4, borderRadius: 2 }} 
        />
      </Box>
    </Box>
  );
};

export default AudioPreview; 