/**
 * Transcript Video Editor - Integrates transcript display with video playback.
 * This component can be easily swapped out with different editor implementations.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Grid,
  Paper,
  Typography,
  Button,
  LinearProgress,
  Alert,
  Chip,
} from '@mui/material';
import {
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  AutoAwesome as ProcessIcon,
} from '@mui/icons-material';

import { VideoPlayer } from '../common/VideoPlayer';
import { TranscriptDisplay } from '../common/TranscriptDisplay';
import { ReorderableTranscript } from './ReorderableTranscript';
import { TranscriptSegment, TranscriptSyncService, SyncState } from '../../services/transcriptSyncService';
import { apiClient } from '../../api/client';

interface TranscriptVideoEditorProps {
  projectId: string;
  videoId: string;
  videoUrl: string;
  videoTitle: string;
  className?: string;
  style?: React.CSSProperties;
}

interface ProcessingJob {
  job_id: string;
  status: 'processing' | 'completed' | 'failed';
  progress: number;
  message: string;
  segment_count?: number;
  duration?: number;
  error?: string;
}

interface VideoClip {
  id: string;
  segment_id: string;
  start_time: number;
  end_time: number;
  duration: number;
  order_index: number;
  stream_url: string;
}

export const TranscriptVideoEditor: React.FC<TranscriptVideoEditorProps> = ({
  projectId,
  videoId,
  videoUrl,
  videoTitle,
  className,
  style,
}) => {
  const [transcriptSegments, setTranscriptSegments] = useState<TranscriptSegment[]>([]);
  const [reorderedSegments, setReorderedSegments] = useState<TranscriptSegment[]>([]);
  const [videoClips, setVideoClips] = useState<VideoClip[]>([]);
  const [syncState, setSyncState] = useState<SyncState>({
    currentSegmentId: null,
    currentWordIndex: -1,
    isPlaying: false,
    currentTime: 0,
  });
  const [processingJob, setProcessingJob] = useState<ProcessingJob | null>(null);
  const [segmentationJob, setSegmentationJob] = useState<ProcessingJob | null>(null);
  const [isLoadingTranscript, setIsLoadingTranscript] = useState(false);
  const [isSegmentingVideo, setIsSegmentingVideo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingMode, setEditingMode] = useState<'view' | 'edit'>('view');
  
  const videoPlayerRef = useRef<any>(null);
  const syncServiceRef = useRef<TranscriptSyncService>(new TranscriptSyncService());
  const progressIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const segmentationIntervalRef = useRef<NodeJS.Timeout | null>(null); // Added for segmentation polling
  const processingJobRef = useRef<ProcessingJob | null>(null); // Add ref for current job state
  const segmentationJobRef = useRef<ProcessingJob | null>(null); // Add ref for current job state

  // Define callback functions BEFORE useEffect hooks to avoid reference errors
  
  const loadExistingTranscript = useCallback(async () => {
    try {
      const segments = await apiClient.getVideoTranscript(projectId, videoId);
      setTranscriptSegments(segments);
      setReorderedSegments(segments); // Initialize reordered segments
      
      if (segments.length > 0) {
        syncServiceRef.current.setSegments(segments);
      }
    } catch (error) {
      console.error('Error loading existing transcript:', error);
    }
  }, [projectId, videoId]);

  const checkProcessingProgress = useCallback(async () => {
    // Get the current processing job from ref (always current)
    const currentJob = processingJobRef.current;
    console.log('checkProcessingProgress called with processingJob:', currentJob);
    if (!currentJob || !currentJob.job_id) {
      console.log('No processing job or job ID available. Current job:', currentJob);
      return;
    }
    
    try {
      console.log(`Checking transcript progress for job ${currentJob.job_id}...`);
      const status = await apiClient.getTranscriptStatus(
        projectId,
        videoId,
        currentJob.job_id
      );
      
      console.log('Transcript status received:', {
        status: status.status,
        progress: status.progress,
        message: status.message,
        job_id: status.job_id,
        video_id: status.video_id,
        project_id: status.project_id
      });
      
      // Preserve the original job_id from the current job if not in response
      const updatedJob = {
        ...status,
        job_id: status.job_id || currentJob.job_id // Keep original job_id if missing from response
      };
      
      console.log('Updated job object:', updatedJob);
      
      setProcessingJob(updatedJob);
      processingJobRef.current = updatedJob; // Update ref as well
      
      if (updatedJob.status === 'completed') {
        console.log('Transcript completed! Clearing interval and loading transcript...');
        
        // Immediately clear the polling interval
        if (progressIntervalRef.current) {
          clearInterval(progressIntervalRef.current);
          progressIntervalRef.current = null;
        }
        
        setIsLoadingTranscript(false);
        await loadExistingTranscript();
        console.log('Transcript loaded successfully');
      } else if (updatedJob.status === 'failed') {
        console.error('Transcript generation failed:', updatedJob.error);
        
        // Clear the polling interval on failure too
        if (progressIntervalRef.current) {
          clearInterval(progressIntervalRef.current);
          progressIntervalRef.current = null;
        }
        
        setError(updatedJob.error || 'Transcript generation failed');
        setIsLoadingTranscript(false);
      }
    } catch (error) {
      console.error('Error checking processing progress:', error);
      
      // Clear interval on error
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
        progressIntervalRef.current = null;
      }
      
      setError('Failed to check transcript status');
      setIsLoadingTranscript(false);
    }
  }, [projectId, videoId, loadExistingTranscript]); // Remove processingJob from dependencies

  const checkSegmentationProgress = useCallback(async () => {
    // Get the current segmentation job from ref (always current)
    const currentJob = segmentationJobRef.current;
    if (!currentJob || !currentJob.job_id) {
      console.log('No segmentation job or job ID available. Current job:', currentJob);
      return;
    }
    
    try {
      console.log(`Checking segmentation progress for job ${currentJob.job_id}...`);
      const status = await apiClient.getSegmentationStatus(
        projectId,
        videoId,
        currentJob.job_id
      );
      
      console.log('Segmentation status received:', {
        status: status.status,
        progress: status.progress,
        message: status.message,
        clipCount: status.clip_count,
        job_id: status.job_id,
        video_id: status.video_id,
        project_id: status.project_id
      });
      
      // Preserve the original job_id from the current job if not in response
      const updatedJob = {
        ...status,
        job_id: status.job_id || currentJob.job_id // Keep original job_id if missing from response
      };
      
      console.log('Updated segmentation job object:', updatedJob);
      
      // Update state immediately
      setSegmentationJob(updatedJob);
      segmentationJobRef.current = updatedJob; // Update ref as well
      
      if (updatedJob.status === 'completed') {
        console.log('Segmentation completed! Clearing interval and setting clips...');
        
        // Immediately clear the polling interval
        if (segmentationIntervalRef.current) {
          clearInterval(segmentationIntervalRef.current);
          segmentationIntervalRef.current = null;
        }
        
        setIsSegmentingVideo(false);
        setVideoClips(status.clips || []);
        setEditingMode('edit');
        console.log(`Set ${status.clips?.length || 0} clips and switched to edit mode`);
      } else if (updatedJob.status === 'failed') {
        console.error('Segmentation failed:', updatedJob.error);
        
        // Clear the polling interval on failure too
        if (segmentationIntervalRef.current) {
          clearInterval(segmentationIntervalRef.current);
          segmentationIntervalRef.current = null;
        }
        
        setError(updatedJob.error || 'Video segmentation failed');
        setIsSegmentingVideo(false);
      }
    } catch (error) {
      console.error('Error checking segmentation progress:', error);
      
      // Clear interval on error
      if (segmentationIntervalRef.current) {
        clearInterval(segmentationIntervalRef.current);
        segmentationIntervalRef.current = null;
      }
      
      setError('Failed to check segmentation status');
      setIsSegmentingVideo(false);
    }
  }, [projectId, videoId]); // Remove segmentationJob from dependencies

  // Initialize transcript sync service
  useEffect(() => {
    const syncService = syncServiceRef.current;
    
    // Add callback for sync state changes
    syncService.addCallback((state) => {
      setSyncState(state);
    });
    
    return () => {
      syncService.stopSync();
      syncService.removeCallback((state) => setSyncState(state));
    };
  }, []);

  // Load existing transcript if available
  useEffect(() => {
    loadExistingTranscript();
  }, [videoId]);

  // Poll for processing job progress
  useEffect(() => {
    // Clear any existing interval first
    if (progressIntervalRef.current) {
      console.log('Clearing existing transcript processing interval');
      clearInterval(progressIntervalRef.current);
      progressIntervalRef.current = null;
    }
    
    if (processingJob && processingJob.status === 'processing') {
      console.log('Starting transcript progress polling for job:', processingJob.job_id);
      progressIntervalRef.current = setInterval(() => {
        checkProcessingProgress();
      }, 2000);
    } else if (processingJob) {
      console.log('Transcript job status is:', processingJob.status);
    }
    
    return () => {
      if (progressIntervalRef.current) {
        console.log('Cleanup: Stopping transcript progress polling');
        clearInterval(progressIntervalRef.current);
        progressIntervalRef.current = null;
      }
    };
  }, [processingJob?.status, processingJob?.job_id]); // Remove checkProcessingProgress from dependencies

  // Poll for segmentation job progress
  useEffect(() => {
    // Clear any existing interval first
    if (segmentationIntervalRef.current) {
      console.log('Clearing existing segmentation interval');
      clearInterval(segmentationIntervalRef.current);
      segmentationIntervalRef.current = null;
    }
    
    if (segmentationJob && segmentationJob.status === 'processing') {
      console.log('Starting segmentation progress polling for job:', segmentationJob.job_id);
      segmentationIntervalRef.current = setInterval(() => {
        checkSegmentationProgress();
      }, 2000);
    } else if (segmentationJob) {
      console.log('Segmentation job status is:', segmentationJob.status);
    }
    
    return () => {
      if (segmentationIntervalRef.current) {
        console.log('Cleanup: Stopping segmentation progress polling');
        clearInterval(segmentationIntervalRef.current);
        segmentationIntervalRef.current = null;
      }
    };
  }, [segmentationJob?.status, segmentationJob?.job_id]); // Remove checkSegmentationProgress from dependencies

  // Add timeout for processing jobs
  useEffect(() => {
    if (processingJob && processingJob.status === 'processing') {
      const timeout = setTimeout(() => {
        console.log('Processing job timeout - forcing completion check');
        checkProcessingProgress();
      }, 30000); // 30 second timeout
      
      return () => clearTimeout(timeout);
    }
  }, [processingJob]);

  const generateTranscript = async () => {
    try {
      setIsLoadingTranscript(true);
      setError(null);
      
      const response = await apiClient.generateTranscript(projectId, videoId);
      
      if (!response.job_id) {
        throw new Error('No job ID returned from server');
      }
      
      const jobData = {
        job_id: response.job_id,
        status: 'processing',
        progress: 0,
        message: response.message,
      };
      setProcessingJob(jobData);
      processingJobRef.current = jobData; // Update ref as well
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Failed to start transcript generation');
      setIsLoadingTranscript(false);
    }
  };

  const handleVideoReady = (videoElement: HTMLVideoElement) => {
    syncServiceRef.current.startSync(videoElement);
  };

  const handleSegmentClick = (segment: TranscriptSegment) => {
    if (videoPlayerRef.current) {
      videoPlayerRef.current.seek(segment.start);
    }
  };

  const handleWordClick = (word: any, segment: TranscriptSegment) => {
    if (videoPlayerRef.current) {
      videoPlayerRef.current.seek(word.start);
    }
  };

  const segmentVideoForEditing = async () => {
    try {
      setIsSegmentingVideo(true);
      setError(null);
      
      const response = await apiClient.segmentVideo(projectId, videoId);
      
      if (!response.job_id) {
        throw new Error('No job ID returned from server');
      }
      
      const jobData = {
        job_id: response.job_id,
        status: 'processing',
        progress: 0,
        message: response.message,
      };
      setSegmentationJob(jobData);
      segmentationJobRef.current = jobData; // Update ref as well
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Failed to start video segmentation');
      setIsSegmentingVideo(false);
    }
  };

  const handleSegmentsReorder = (reorderedSegments: TranscriptSegment[]) => {
    setReorderedSegments(reorderedSegments);
    // TODO: Update video playback to reflect new order
    console.log('Segments reordered:', reorderedSegments.map(s => s.text));
  };

  const handleSegmentVideo = (segment: TranscriptSegment) => {
    console.log('Creating video clip for segment:', segment.text);
    // This will be handled by the segmentation service
  };

  const hasTranscript = transcriptSegments.length > 0;
  const isProcessing = processingJob?.status === 'processing';

  return (
    <Box className={className} style={style} sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header Section */}
      <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}>
        <Typography variant="h6" gutterBottom>
          {videoTitle}
        </Typography>
        
        {!hasTranscript && !isProcessing && (
          <Button
            variant="contained"
            startIcon={<ProcessIcon />}
            onClick={generateTranscript}
            disabled={isLoadingTranscript}
            sx={{ mb: 2 }}
          >
            Generate Transcript for Editing
          </Button>
        )}
        
        {isProcessing && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              {processingJob.message}
            </Typography>
            <LinearProgress 
              variant="determinate" 
              value={processingJob.progress}
              sx={{ mb: 1 }}
            />
            <Typography variant="caption" color="text.secondary">
              {processingJob.progress}% complete
            </Typography>
          </Box>
        )}
        
        {hasTranscript && (
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
            <Chip 
              label={`${transcriptSegments.length} segments`}
              size="small"
              color="primary"
            />
            <Chip 
              label="Ready for editing"
              size="small"
              color="success"
            />
            <Button 
              size="small" 
              onClick={loadExistingTranscript}
            >
              Refresh
            </Button>
          </Box>
        )}
        
        {!hasTranscript && !isProcessing && (
          <Button 
            size="small" 
            onClick={loadExistingTranscript}
          >
            Check for Transcript
          </Button>
        )}
      </Box>

      {/* Main Content Area */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: { xs: 'column', lg: 'row' }, minHeight: 0 }}>
        {/* Video Player */}
        <Box sx={{ flex: { xs: 1, lg: 2 }, minHeight: { xs: '300px', lg: 'auto' }, display: 'flex', flexDirection: 'column' }}>
          <Paper sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
              <VideoPlayer
                ref={videoPlayerRef}
                src={videoUrl}
                title={videoTitle}
                onVideoReady={handleVideoReady}
                style={{ flex: 1, minHeight: 0 }}
              />
            </Box>
          </Paper>
        </Box>

        {/* Transcript Display */}
        <Box sx={{ flex: { xs: 1, lg: 1 }, minHeight: { xs: '300px', lg: 'auto' }, display: 'flex', flexDirection: 'column' }}>
          <Paper sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}>
              <Typography variant="h6">
                Transcript
                {syncState.currentSegmentId && (
                  <Chip 
                    label="Live Sync"
                    size="small"
                    color="primary"
                    sx={{ ml: 1 }}
                  />
                )}
              </Typography>
            </Box>
            
            <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
              {error && (
                <Alert severity="error" sx={{ m: 2 }}>
                  {error}
                </Alert>
              )}
              
              {!hasTranscript && !isProcessing && (
                <Box sx={{ p: 4, textAlign: 'center' }}>
                  <Typography variant="body2" color="text.secondary">
                    No transcript available. Generate a transcript to enable text-based editing.
                  </Typography>
                </Box>
              )}
              
              {hasTranscript && (
                <>
                  {/* Mode Toggle and Controls */}
                  <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}>
                    <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
                      <Button
                        variant={editingMode === 'view' ? 'contained' : 'outlined'}
                        size="small"
                        onClick={() => setEditingMode('view')}
                      >
                        View Mode
                      </Button>
                      <Button
                        variant={editingMode === 'edit' ? 'contained' : 'outlined'}
                        size="small"
                        onClick={() => setEditingMode('edit')}
                        disabled={videoClips.length === 0}
                      >
                        Edit Mode
                      </Button>
                      
                      {hasTranscript && videoClips.length === 0 && (
                        <Button
                          variant="outlined"
                          size="small"
                          startIcon={<ProcessIcon />}
                          onClick={segmentVideoForEditing}
                          disabled={isSegmentingVideo}
                        >
                          {isSegmentingVideo ? 'Segmenting...' : 'Segment Video'}
                        </Button>
                      )}
                    </Box>
                  </Box>

                  {/* Segmentation Progress */}
                  {segmentationJob && segmentationJob.status === 'processing' && (
                    <Box sx={{ p: 2, flexShrink: 0 }}>
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                        {segmentationJob.message}
                      </Typography>
                      <LinearProgress variant="determinate" value={segmentationJob.progress} sx={{ mb: 1 }} />
                      <Typography variant="body2" color="text.secondary">
                        {segmentationJob.progress}% complete
                      </Typography>
                    </Box>
                  )}

                  {/* Transcript Content */}
                  <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
                    {editingMode === 'view' ? (
                      <TranscriptDisplay
                        segments={transcriptSegments}
                        currentSegmentId={syncState.currentSegmentId}
                        currentWordIndex={syncState.currentWordIndex}
                        onSegmentClick={handleSegmentClick}
                        onWordClick={handleWordClick}
                        showSpeakers={true}
                        showConfidence={false}
                        style={{ height: '100%' }}
                      />
                    ) : (
                      <ReorderableTranscript
                        segments={reorderedSegments}
                        currentSegmentId={syncState.currentSegmentId}
                        currentWordIndex={syncState.currentWordIndex}
                        onSegmentsReorder={handleSegmentsReorder}
                        onSegmentClick={handleSegmentClick}
                        onWordClick={handleWordClick}
                        onSegmentVideo={handleSegmentVideo}
                        showSpeakers={true}
                        showConfidence={false}
                        style={{ height: '100%' }}
                      />
                    )}
                  </Box>
                </>
              )}
            </Box>
          </Paper>
        </Box>
      </Box>
    </Box>
  );
};
