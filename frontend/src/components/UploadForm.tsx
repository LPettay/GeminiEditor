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
  Alert,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Checkbox,
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
  prompt?: string;
  enableVisionExtension?: boolean;
  enableMultimodalPass2?: boolean;
  simpleMode?: boolean;
}

// utility to extract filename from FileList
const emptyFileList: FileList = new DataTransfer().files;

interface Props {
  onSubmit: (data: UploadFormValues) => void;
  isSubmitting?: boolean;
}

// Preset prompts for different video styles
const PRESET_PROMPTS = {
  default: "Create a highly entertaining video edited in the style of popular online comedians like Jerma985, BedBanana, or General Sam. Focus on highlighting the speaker's unique personality, comedic timing, absurd moments, and genuine reactions. Prioritize fast-paced, funny, and engaging mini-narratives or highlight reel moments. If there are setups and punchlines for jokes, try to capture them.",
  educational: "Create an educational video that clearly explains concepts and maintains viewer engagement. Focus on clear explanations, visual demonstrations, and logical flow. Highlight key learning moments and ensure the content is easy to follow and understand.",
  gaming: "Create an exciting gaming highlight reel that showcases the best moments, epic plays, and funny reactions. Focus on action-packed sequences, clutch moments, and entertaining commentary. Make it fast-paced and engaging for gaming audiences.",
  vlog: "Create a personal vlog-style video that captures authentic moments and tells a compelling story. Focus on genuine emotions, personal insights, and natural flow. Highlight meaningful interactions and create a narrative that connects with viewers."
};

const UploadForm: React.FC<Props> = ({ onSubmit, isSubmitting }) => {
  const {
    control,
    handleSubmit,
    register,
    watch,
    setValue,
    formState: { errors },
  } = useForm<UploadFormValues>({
    defaultValues: { scopeStart: undefined, scopeEnd: undefined, prompt: '', enableVisionExtension: false, enableMultimodalPass2: true, simpleMode: false },
  });

  const watchedFiles = watch('video');

  const [analysisDone, setAnalysisDone] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [isProcessing, setIsProcessing] = useState(false); // server processing stage
  const [jobId, setJobId] = useState<string | null>(null);
  const [logLines, setLogLines] = useState<string[]>([]);
  // UI step: 0=file select, 1=upload/analyze, 2=audio track, 3=scope, 4=prompt & submit
  const [activeStep, setActiveStep] = useState(0);
  const [originalName, setOriginalName] = useState<string | null>(null);
  const [isDuplicate, setIsDuplicate] = useState(false);
  const [isCheckingDuplicate, setIsCheckingDuplicate] = useState(false);

  // Waveform peaks are no longer needed

  const checkDuplicateMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('filename', file.name);
      formData.append('size', String(file.size));
      formData.append('last_modified', String(file.lastModified));
      
      const res = await axios.post('/check-duplicate', formData);
      return res.data as { duplicate: boolean; file_id?: string; message: string };
    },
  });

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
      // /analyze now returns { job_id: string, duplicate?: boolean }
      return res.data as { job_id: string; duplicate?: boolean };
    },
    onMutate: () => {
      setUploadProgress(0);
      setIsProcessing(false);
      setJobId(null);
      setLogLines([]);
      setIsDuplicate(false);
    },
    onSuccess: (data) => {
      const jid = data.job_id;
      setJobId(jid);
      setIsDuplicate(data.duplicate || false);
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
    setIsDuplicate(false);
    setIsCheckingDuplicate(false);
    
    if (watchedFiles && watchedFiles.length > 0) {
      const file = watchedFiles[0];
      setOriginalName(file.name);
      setActiveStep(1);
      
      // First check if this is a duplicate
      setIsCheckingDuplicate(true);
      checkDuplicateMutation.mutate(file, {
        onSuccess: (data) => {
          setIsCheckingDuplicate(false);
          if (data.duplicate) {
            setIsDuplicate(true);
            // If it's a duplicate, we can skip the upload and go directly to analysis
            // We'll need to get the existing file_id and start analysis
            if (data.file_id) {
              setJobId(data.file_id);
              // For duplicates, call analyze with just the file_id (no file upload)
              const fd = new FormData();
              fd.append('preview_duration', String(20));
              fd.append('file_id', data.file_id);
              
              axios.post('/analyze', fd, {
                headers: { 'Content-Type': 'multipart/form-data' },
              }).then((res) => {
                const responseData = res.data as { job_id: string; duplicate?: boolean };
                setJobId(responseData.job_id);
                setIsDuplicate(responseData.duplicate || false);
                setIsProcessing(true); // Start processing immediately for duplicates
              }).catch((error) => {
                console.error('Error starting analysis for duplicate:', error);
                setLogLines((prev) => [...prev, `Error: ${error.message}`]);
              });
            }
          } else {
            // Not a duplicate, proceed with normal upload
            analyzeMutation.mutate(file);
          }
        },
        onError: () => {
          setIsCheckingDuplicate(false);
          // If duplicate check fails, proceed with normal upload
          analyzeMutation.mutate(file);
        }
      });
    } else {
      setActiveStep(0);
    }
  }, [watchedFiles]); // Removed setValue from dependencies

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
  }, [jobId]); // Removed setValue from dependencies

  return (
    <Box 
      component="form" 
      onSubmit={handleSubmit(onSubmit)} 
      noValidate
      sx={{
        width: '100%',
        maxWidth: '600px',
        mx: 'auto',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center'
      }}
    >
      <Stepper activeStep={activeStep} alternativeLabel sx={{ mb: 3, width: '100%' }}>
        {['Select file', 'Analyzing', 'Pick audio', 'Set scope', 'Configure prompt'].map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      <Stack spacing={2} sx={{ width: '100%' }}>
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
            {/* Checking for duplicates */}
            {isCheckingDuplicate && (
              <>
                <Typography variant="body2">Checking if file has been uploaded before...</Typography>
                <LinearProgress variant="indeterminate" />
              </>
            )}
            
            {/* Duplicate file notification */}
            {isDuplicate && !isCheckingDuplicate && (
              <Alert severity="info" sx={{ mb: 2 }}>
                <Typography variant="body2">
                  This file has been uploaded before. Using the previously uploaded version to save time and storage.
                </Typography>
              </Alert>
            )}
            
            {/* Uploading stage */}
            {uploadProgress !== null && !isProcessing && !isCheckingDuplicate && (
              <>
                <Typography variant="body2">Uploading… {uploadProgress}%</Typography>
                <LinearProgress variant="determinate" value={uploadProgress} />
              </>
            )}
            {/* Server-side processing stage */}
            {isProcessing && !isCheckingDuplicate && (
              <>
                <Typography variant="body2">
                  {isDuplicate ? "Processing previously uploaded file…" : "Processing audio…"}
                </Typography>
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
              videoUrl={`/video/${jobId}_${encodeURIComponent(originalName)}`}
              onRangeChange={(inn, out) => {
                setValue('scopeStart', inn);
                setValue('scopeEnd', out);
              }}
            />
            <Button variant="contained" onClick={() => setActiveStep(4)} sx={{ mt: 2 }}>
              Next
            </Button>
          </>
        )}

        {activeStep === 4 && (
          <>
            <Typography variant="h6">Configure AI Prompt</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Customize how the AI will edit your video. Leave empty to use the default prompt.
            </Typography>
            
            <FormControl fullWidth sx={{ mb: 2 }}>
              <InputLabel>Preset Style</InputLabel>
              <Controller
                name="prompt"
                control={control}
                render={({ field }) => (
                  <Select
                    {...field}
                    label="Preset Style"
                    value={Object.keys(PRESET_PROMPTS).find(key => PRESET_PROMPTS[key as keyof typeof PRESET_PROMPTS] === field.value) || 'custom'}
                    onChange={(e) => {
                      const value = e.target.value;
                      if (value === 'custom') {
                        field.onChange('');
                      } else {
                        field.onChange(PRESET_PROMPTS[value as keyof typeof PRESET_PROMPTS]);
                      }
                    }}
                  >
                    <MenuItem value="default">Default (Comedy/Entertainment)</MenuItem>
                    <MenuItem value="educational">Educational/Tutorial</MenuItem>
                    <MenuItem value="gaming">Gaming Highlights</MenuItem>
                    <MenuItem value="vlog">Vlog/Personal</MenuItem>
                    <MenuItem value="custom">Custom (write your own)</MenuItem>
                  </Select>
                )}
              />
            </FormControl>

            <Controller
              name="prompt"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  fullWidth
                  multiline
                  rows={4}
                  label="Custom Prompt"
                  placeholder="Describe how you want the AI to edit your video..."
                  helperText="Be specific about the style, pacing, and what moments to highlight"
                  variant="outlined"
                />
              )}
            />

            <Box sx={{ mt: 3, p: 2, bgcolor: 'background.paper', borderRadius: 1, border: 1, borderColor: 'divider' }}>
              <Typography variant="h6" sx={{ mb: 1 }}>Advanced Options</Typography>
              <Controller
                name="enableVisionExtension"
                control={control}
                render={({ field }) => (
                  <FormControlLabel
                    control={
                      <Checkbox
                        {...field}
                        checked={field.value || false}
                        onChange={(e) => field.onChange(e.target.checked)}
                      />
                    }
                    label={
                      <Box>
                        <Typography variant="body2">
                          Enable AI Video Extension
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Use AI vision analysis to automatically extend video clips for better context. 
                          Requires Gemini API key and may increase processing time.
                        </Typography>
                      </Box>
                    }
                  />
                )}
              />
              
              <Controller
                name="enableMultimodalPass2"
                control={control}
                render={({ field }) => (
                  <FormControlLabel
                    control={
                      <Checkbox
                        {...field}
                        checked={field.value || false}
                        onChange={(e) => field.onChange(e.target.checked)}
                      />
                    }
                    label={
                      <Box>
                        <Typography variant="body2">
                          Enable Multimodal AI Analysis
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Upload video to Google for advanced AI analysis and refinement. 
                          Disable to skip upload and use only local processing.
                        </Typography>
                      </Box>
                    }
                  />
                )}
              />
              
              <Controller
                name="simpleMode"
                control={control}
                render={({ field }) => (
                  <FormControlLabel
                    control={
                      <Checkbox
                        {...field}
                        checked={field.value || false}
                        onChange={(e) => field.onChange(e.target.checked)}
                      />
                    }
                    label={
                      <Box>
                        <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                          Simple Mode (Recommended)
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Skip all complex processing. Just concatenate selected clips based on your prompt. 
                          Clean, fast, no quality issues.
                        </Typography>
                      </Box>
                    }
                  />
                )}
              />
            </Box>

            <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
              <Button variant="outlined" onClick={() => setActiveStep(3)}>
                Back
              </Button>
              <Button type="submit" variant="contained" disabled={isSubmitting}>
                {isSubmitting ? 'Processing…' : 'Start Processing'}
              </Button>
            </Stack>
          </>
        )}
      </Stack>
    </Box>
  );
};

export default UploadForm; 