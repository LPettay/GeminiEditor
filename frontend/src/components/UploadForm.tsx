import { useForm, Controller } from 'react-hook-form';
import {
  Box,
  Button,
  Stack,
  Typography,
  RadioGroup,
  FormControlLabel,
  Radio,
  CircularProgress,
  LinearProgress,
  Stepper,
  Step,
  StepLabel,
} from '@mui/material';
import { useMutation } from '@tanstack/react-query';
import axios from 'axios';
import { useEffect, useState } from 'react';
import WaveformPreview from './WaveformPreview';
import DebugPanel from './DebugPanel';
import VideoScrubber from './VideoScrubber';

export interface UploadFormValues {
  video: FileList;
  scopeStart?: number;
  scopeEnd?: number;
  audioTrack?: number;
  fileId?: string;
}

// utility to extract filename from FileList
const emptyFileList: FileList = new DataTransfer().files;

interface Props {
  onSubmit: (data: UploadFormValues) => void;
  isSubmitting?: boolean;
}

const UploadForm: React.FC<Props> = ({ onSubmit, isSubmitting }) => {
  const {
    control,
    handleSubmit,
    register,
    watch,
    setValue,
    formState: { errors },
  } = useForm<UploadFormValues>({
    defaultValues: { scopeStart: undefined, scopeEnd: undefined },
  });

  const watchedFiles = watch('video');

  const [analysisDone, setAnalysisDone] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [isProcessing, setIsProcessing] = useState(false); // server processing stage
  const [jobId, setJobId] = useState<string | null>(null);
  const [logLines, setLogLines] = useState<string[]>([]);
  // UI step: 0=file select, 1=upload/analyze, 2=audio track, 3=scope & submit
  const [activeStep, setActiveStep] = useState(0);
  const [originalName, setOriginalName] = useState<string | null>(null);

  // Waveform peaks are no longer needed

  const analyzeMutation = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('preview_duration', String(20)); // 20 second previews
      const res = await axios.post('/analyze', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (e.total) {
            const percent = Math.round((e.loaded * 100) / e.total);
            setUploadProgress(percent);
            if (percent >= 100) {
              setIsProcessing(true);
            }
          }
        },
      });
      // /analyze now returns { job_id: string }
      return res.data as { job_id: string };
    },
    onMutate: () => {
      setUploadProgress(0);
      setIsProcessing(false);
      setJobId(null);
      setLogLines([]);
    },
    onSuccess: (data) => {
      const jid = data.job_id;
      setJobId(jid);
      // isProcessing already true when upload reached 100
    },
    onSettled: () => {
      setUploadProgress(null);
    },
  });

  const [tracks, setTracks] = useState<any[]>([]);

  // Reset analysis when user picks a different file
  useEffect(() => {
    setAnalysisDone(false);
    setTracks([]);
    setValue('fileId', undefined as any);
    setValue('audioTrack', undefined);
    if (watchedFiles && watchedFiles.length > 0) {
      setActiveStep(1);
      analyzeMutation.mutate(watchedFiles[0]);
      setOriginalName(watchedFiles[0].name);
    } else {
      setActiveStep(0);
    }
  }, [watchedFiles, setValue]);

  // Subscribe to SSE progress once we have a jobId
  useEffect(() => {
    if (!jobId) return;

    const es = new EventSource(`/progress/${jobId}`);

    es.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'done') {
          const payload = msg.payload as { file_id: string; tracks: any[]; original_filename?: string };
          setIsProcessing(false);
          setAnalysisDone(true);
          setTracks(payload.tracks);
          if (payload.original_filename) setOriginalName(payload.original_filename);
          setValue('fileId', payload.file_id);
          if (payload.tracks?.length) {
            setValue('audioTrack', payload.tracks[0].idx);
          }
          setActiveStep(2);
          es.close();
        } else if (msg.type === 'error') {
          setIsProcessing(false);
          setLogLines((prev) => [...prev, `Error: ${msg.text}`]);
        } else if (msg.text) {
          setLogLines((prev) => [...prev, msg.text]);
        }
      } catch (_) {
        /* ignore parse errors */
      }
    };

    es.onerror = () => {
      setIsProcessing(false);
      es.close();
    };

    return () => es.close();
  }, [jobId, setValue]);

  return (
    <Box component="form" onSubmit={handleSubmit(onSubmit)} noValidate>
      <Stepper activeStep={activeStep} alternativeLabel sx={{ mb: 3 }}>
        {['Select file', 'Analyzing', 'Pick audio', 'Scope & submit'].map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      <Stack spacing={2}>
        {activeStep === 0 && (
          <Button variant="outlined" component="label">
            Select video file
            <input
              type="file"
              accept="video/*,.mkv,.mp4,.mov,.avi"
              hidden
              {...register('video', { required: 'Please choose a video file' })}
            />
          </Button>
        )}
        {/* show selected file name */}
        {watchedFiles && watchedFiles.length > 0 && (
          <Typography variant="body2" color="text.secondary">
            Selected: {watchedFiles[0].name}
          </Typography>
        )}
        {errors.video && (
          <Typography color="error" variant="caption">
            {errors.video.message}
          </Typography>
        )}

        {activeStep === 1 && (
          <Stack spacing={1} width="100%">
            {/* Uploading stage */}
            {uploadProgress !== null && !isProcessing && (
              <>
                <Typography variant="body2">Uploading… {uploadProgress}%</Typography>
                <LinearProgress variant="determinate" value={uploadProgress} />
              </>
            )}
            {/* Server-side processing stage */}
            {isProcessing && (
              <>
                <Typography variant="body2">Processing audio…</Typography>
                <LinearProgress variant="indeterminate" />
                <Box sx={{ pl: 2, pt: 1 }}>
                  {logLines.map((l, i) => (
                    <Typography key={i} variant="caption" display="block">
                      • {l}
                    </Typography>
                  ))}
                </Box>
              </>
            )}
          </Stack>
        )}

        {activeStep === 2 && (
          <>
            <Typography variant="h6">Select audio track</Typography>
            {analyzeMutation.isPending && <CircularProgress size={16} />}
            {/* Debug info in development */}
            {import.meta.env.DEV && (
              <DebugPanel 
                title="Debug: Current State" 
                data={{
                  activeStep,
                  jobId,
                  tracks: tracks.map(t => ({ idx: t.idx, snippet_url: t.snippet_url, codec: t.codec })),
                  selectedTrack: watch('audioTrack'),
                  fileId: watch('fileId')
                }}
              />
            )}
            <Controller
              name="audioTrack"
              control={control}
              rules={{ required: 'Choose a track' }}
              render={({ field }) => (
                <RadioGroup {...field}>
                  {tracks.map((t) => (
                    <FormControlLabel
                      key={t.idx}
                      value={t.idx}
                      control={<Radio />}
                      label={
                        <Stack direction="row" spacing={2} alignItems="center">
                          <Box sx={{ flexGrow: 1 }}>
                            <WaveformPreview url={t.snippet_url ?? t.preview_url} peaksUrl={t.peaks_url} />
                            <Typography variant="caption" color="text.secondary">
                              Track {t.idx} – {t.codec}, {t.channels}ch, {t.lang}
                            </Typography>
                          </Box>
                        </Stack>
                      }
                    />
                  ))}
                </RadioGroup>
              )}
            />

            <Button variant="contained" onClick={() => setActiveStep(3)} disabled={!watch('audioTrack')}>
              Next
            </Button>
          </>
        )}

        {activeStep === 3 && originalName && jobId && (
          <>
            <VideoScrubber
              videoUrl={`/uploads/${jobId}_${encodeURIComponent(originalName)}`}
              onConfirm={(inn, out) => {
                setValue('scopeStart', inn);
                setValue('scopeEnd', out);
              }}
            />
            <Button type="submit" variant="contained" disabled={isSubmitting} sx={{ mt: 2 }}>
              {isSubmitting ? 'Processing…' : 'Start Processing'}
            </Button>
          </>
        )}
      </Stack>
    </Box>
  );
};

export default UploadForm; 