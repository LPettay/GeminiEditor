import { useEffect, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';
import { Box, IconButton } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';

interface Props {
  url: string;
  peaksUrl?: string;
  height?: number;
  color?: string;
  onReady?: () => void;
}

const WaveformPreview: React.FC<Props> = ({ url, peaksUrl, height = 64, color = '#2196f3', onReady }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const wavesurferRef = useRef<WaveSurfer | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;

    const createWs = (peaks?: any) => {
      const wsInstance = WaveSurfer.create({
        container: containerRef.current as HTMLElement,
        waveColor: color,
        progressColor: '#1976d2',
        height,
        normalize: true,
        barWidth: 2,
        cursorWidth: 1,
        // @ts-expect-error upstream types missing
        responsive: true,
        // The default renderer draws the waveform mirrored around the X-axis.
        // We'll keep the default rendering and later crop the bottom half via CSS.
        peaks,
      });
      wsInstance.load(url);
      wsInstance.on('ready', () => {
        // Crop the waveform canvases so only the top half is visible
        const canvases = containerRef.current?.shadowRoot?.querySelectorAll('canvas');
        canvases?.forEach((canvas) => {
          (canvas as HTMLCanvasElement).style.clipPath = 'inset(0 0 50% 0)';
        });
        onReady?.();
      });
      wsInstance.on('finish', () => setIsPlaying(false));
      wavesurferRef.current = wsInstance;
      return wsInstance;
    };

    let ws: WaveSurfer | null = null;

    if (peaksUrl) {
      fetch(peaksUrl)
        .then((r) => r.json())
        .then((p) => {
          const raw = p.data ?? p;
          const single = Array.isArray(raw[0]) ? raw[0] : raw;
          ws = createWs(single);
        })
        .catch(() => {
          ws = createWs();
        });
    } else {
      ws = createWs();
    }

    // events already attached inside createWs

    // Resize observer to redraw on width change
    const ro = new ResizeObserver(() => {
      const wsAny = wavesurferRef.current as any;
      if (wsAny && wsAny.drawBuffer) wsAny.drawBuffer();
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      wavesurferRef.current?.destroy();
    };
  }, [url, peaksUrl, color, height, onReady]);

  const togglePlay = () => {
    if (!wavesurferRef.current) return;
    wavesurferRef.current.playPause();
    setIsPlaying(wavesurferRef.current.isPlaying());
  };

  return (
    <Box display="flex" alignItems="center" width="100%">
      <IconButton onClick={togglePlay} size="small" sx={{ mr: 1 }}>
        {isPlaying ? <PauseIcon /> : <PlayArrowIcon />}
      </IconButton>
      <Box sx={{ flexGrow: 1, minWidth: 300 }} ref={containerRef} />
    </Box>
  );
};

export default WaveformPreview; 