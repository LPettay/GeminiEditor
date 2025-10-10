/**
 * Edit Editor Page - Complete text-based editing interface
 */

import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Box,
  Typography,
  IconButton,
  CircularProgress,
  Alert,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  LinearProgress,
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Publish as FinalizeIcon,
} from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';
import { useEditorStore } from '../store/editorStore';
import SequentialVideoPlayer from '../components/editor/SequentialVideoPlayer';
import TranscriptTimeline from '../components/editor/TranscriptTimeline';
import TrimExtendModal from '../components/editor/TrimExtendModal';

export default function EditEditorPage() {
  const { projectId, editId } = useParams<{ projectId: string; editId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  
  const {
    setCurrentEdit,
    setEditDecisions,
    editDecisions,
    currentClipIndex,
    setCurrentClipIndex,
  } = useEditorStore();

  const [editingDecisionId, setEditingDecisionId] = useState<string | null>(null);
  const [finalizeDialogOpen, setFinalizeDialogOpen] = useState(false);
  const [finalizeJobId, setFinalizeJobId] = useState<string | null>(null);
  const [finalizeProgress, setFinalizeProgress] = useState(0);

  // Fetch edit with decisions
  const { data: edit, isLoading, error } = useQuery({
    queryKey: ['edit', projectId, editId],
    queryFn: async () => {
      const data = await apiClient.getEditWithDecisions(projectId!, editId!);
      setCurrentEdit(data);
      setEditDecisions(data.edit_decisions || []);
      return data;
    },
    enabled: !!projectId && !!editId,
  });

  // Fetch preview data
  const { data: previewData } = useQuery({
    queryKey: ['editPreview', projectId, editId],
    queryFn: () => apiClient.getEditPreview(projectId!, editId!),
    enabled: !!projectId && !!editId && !!edit,
  });

  // Save edit mutation
  const saveMutation = useMutation({
    mutationFn: async () => {
      // Save each modified decision
      const updates = editDecisions.filter(d => d.user_modified);
      for (const decision of updates) {
        await apiClient.updateEditDecision(projectId!, editId!, decision.id, {
          order_index: decision.order_index,
          start_time: decision.start_time,
          end_time: decision.end_time,
          is_included: decision.is_included,
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['edit', projectId, editId] });
      queryClient.invalidateQueries({ queryKey: ['editPreview', projectId, editId] });
    },
  });

  // Finalize mutation
  const finalizeMutation = useMutation({
    mutationFn: () => apiClient.finalizeEdit(projectId!, editId!, {}),
    onSuccess: (data) => {
      setFinalizeJobId(data.job_id);
      // Start polling for progress
      pollFinalizeProgress(data.job_id);
    },
  });

  // Poll finalize progress
  const pollFinalizeProgress = async (jobId: string) => {
    const interval = setInterval(async () => {
      try {
        const status = await apiClient.getJobStatus(jobId);
        setFinalizeProgress(status.progress);
        
        if (status.status === 'completed') {
          clearInterval(interval);
          setFinalizeDialogOpen(false);
          setFinalizeJobId(null);
          queryClient.invalidateQueries({ queryKey: ['edit', projectId, editId] });
          // Show success message
          alert('Edit finalized successfully!');
        } else if (status.status === 'failed') {
          clearInterval(interval);
          alert(`Finalization failed: ${status.message}`);
        }
      } catch (err) {
        clearInterval(interval);
        console.error('Error polling progress:', err);
      }
    }, 1000);
  };

  const handleSave = async () => {
    await saveMutation.mutateAsync();
  };

  const handleFinalize = () => {
    if (confirm('Finalize this edit? This will create the final video file.')) {
      finalizeMutation.mutate();
    }
  };

  if (isLoading) {
    return (
      <Container sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <CircularProgress />
      </Container>
    );
  }

  if (error || !edit) {
    return (
      <Container sx={{ py: 4 }}>
        <Alert severity="error">Failed to load edit: {error?.toString() || 'Unknown error'}</Alert>
      </Container>
    );
  }

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Box
        sx={{
          px: 3,
          py: 2,
          borderBottom: 1,
          borderColor: 'divider',
          display: 'flex',
          alignItems: 'center',
          gap: 2,
        }}
      >
        <IconButton onClick={() => navigate(`/projects/${projectId}`)}>
          <ArrowBackIcon />
        </IconButton>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h5">{edit.name}</Typography>
          <Typography variant="caption" color="text.secondary">
            Version {edit.version} • {edit.is_finalized ? 'Finalized' : 'Draft'}
          </Typography>
        </Box>
        <Button
          variant="contained"
          color="success"
          startIcon={<FinalizeIcon />}
          onClick={() => setFinalizeDialogOpen(true)}
          disabled={edit.is_finalized}
        >
          {edit.is_finalized ? 'Already Finalized' : 'Finalize & Export'}
        </Button>
      </Box>

      {/* Main Content - Split View */}
      <Box sx={{ flexGrow: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left: Video Player */}
        <Box sx={{ width: '50%', p: 2, overflow: 'auto' }}>
          {previewData ? (
            <SequentialVideoPlayer
              clips={previewData.clips}
              projectId={projectId!}
              editId={editId!}
              onTimeUpdate={(time, clipIndex) => {
                setCurrentClipIndex(clipIndex);
              }}
              onClipChange={(clipIndex) => {
                setCurrentClipIndex(clipIndex);
              }}
            />
          ) : (
            <Alert severity="info">Loading preview...</Alert>
          )}
        </Box>

        {/* Right: Transcript Timeline */}
        <Box
          sx={{
            width: '50%',
            borderLeft: 1,
            borderColor: 'divider',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <TranscriptTimeline
            decisions={editDecisions}
            currentClipIndex={currentClipIndex}
            onSave={handleSave}
            onEditDecision={(decisionId) => setEditingDecisionId(decisionId)}
          />
        </Box>
      </Box>

      {/* Trim/Extend Modal */}
      {editingDecisionId && (
        <TrimExtendModal
          decision={editDecisions.find(d => d.id === editingDecisionId)!}
          onClose={() => setEditingDecisionId(null)}
          onSave={(updates) => {
            // Update in store
            const decision = editDecisions.find(d => d.id === editingDecisionId);
            if (decision) {
              setEditDecisions(
                editDecisions.map(d =>
                  d.id === editingDecisionId ? { ...d, ...updates, user_modified: true } : d
                )
              );
            }
            setEditingDecisionId(null);
          }}
        />
      )}

      {/* Finalize Dialog */}
      <Dialog open={finalizeDialogOpen} onClose={() => !finalizeJobId && setFinalizeDialogOpen(false)}>
        <DialogTitle>Finalize Edit</DialogTitle>
        <DialogContent>
          {finalizeJobId ? (
            <Box sx={{ minWidth: 400 }}>
              <Typography gutterBottom>Finalizing edit...</Typography>
              <LinearProgress variant="determinate" value={finalizeProgress} sx={{ my: 2 }} />
              <Typography variant="body2" color="text.secondary">
                {finalizeProgress}% complete
              </Typography>
            </Box>
          ) : (
            <Box sx={{ minWidth: 400 }}>
              <Alert severity="info" sx={{ mb: 2 }}>
                This will create the final video file by concatenating all included segments.
                The process may take several minutes depending on the video length.
              </Alert>
              <Typography variant="body2">
                <strong>Edit:</strong> {edit.name}
              </Typography>
              <Typography variant="body2">
                <strong>Segments:</strong> {editDecisions.filter(d => d.is_included).length}
              </Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          {!finalizeJobId && (
            <>
              <Button onClick={() => setFinalizeDialogOpen(false)}>Cancel</Button>
              <Button onClick={handleFinalize} variant="contained" color="success">
                Finalize
              </Button>
            </>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
}
