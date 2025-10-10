/**
 * Source Videos Tab - Shows and manages source videos for a project
 */

import { useState } from 'react';
import {
  Box,
  Button,
  Typography,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  CircularProgress,
  Alert,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
} from '@mui/material';
import {
  Upload as UploadIcon,
  PlayArrow as PlayIcon,
  Delete as DeleteIcon,
  Subtitles as SubtitlesIcon,
  Close as CloseIcon,
} from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';
import VideoUploadDialog from '../common/VideoUploadDialog';
import VideoPreviewDialog from '../common/VideoPreviewDialog';
import { TranscriptVideoEditor } from '../editor/TranscriptVideoEditor';

interface SourceVideosTabProps {
  projectId: string;
}

export default function SourceVideosTab({ projectId }: SourceVideosTabProps) {
  const queryClient = useQueryClient();
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [previewDialogOpen, setPreviewDialogOpen] = useState(false);
  const [previewVideo, setPreviewVideo] = useState<{ id: string; filename: string } | null>(null);
  const [editorVideo, setEditorVideo] = useState<{ id: string; filename: string; url: string } | null>(null);

  // Fetch source videos
  const { data: videos, isLoading, error } = useQuery({
    queryKey: ['sourceVideos', projectId],
    queryFn: () => apiClient.getSourceVideos(projectId),
  });

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: ({ file, onProgress }: { file: File; onProgress: (progress: number) => void }) =>
      apiClient.uploadSourceVideo(projectId, file, onProgress),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sourceVideos', projectId] });
      setUploadDialogOpen(false);
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (videoId: string) => apiClient.deleteSourceVideo(projectId, videoId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sourceVideos', projectId] });
    },
  });

  const formatDuration = (seconds?: number) => {
    if (!seconds) return 'Unknown';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return 'Unknown';
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(2)} MB`;
  };

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">Failed to load source videos</Alert>;
  }

  return (
    <Box>
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h6">Source Videos</Typography>
        <Button 
          variant="contained" 
          startIcon={<UploadIcon />}
          onClick={() => setUploadDialogOpen(true)}
        >
          Upload Video
        </Button>
      </Box>

      {!videos || videos.length === 0 ? (
        <Alert severity="info">
          No source videos yet. Upload a video to get started.
        </Alert>
      ) : (
        <List>
          {videos.map((video) => (
            <ListItem
              key={video.id}
              sx={{
                border: 1,
                borderColor: 'divider',
                borderRadius: 1,
                mb: 1,
                '&:hover': { bgcolor: 'action.hover' },
              }}
            >
              <ListItemText
                primary={video.filename}
                secondary={
                  <Box sx={{ mt: 1 }}>
                    <Chip label={formatDuration(video.duration)} size="small" sx={{ mr: 1 }} />
                    <Chip label={formatFileSize(video.file_size)} size="small" sx={{ mr: 1 }} />
                    {video.transcript_path && (
                      <Chip
                        icon={<SubtitlesIcon />}
                        label="Transcribed"
                        color="primary"
                        size="small"
                      />
                    )}
                  </Box>
                }
                secondaryTypographyProps={{
                  component: 'div'
                }}
              />
              <ListItemSecondaryAction>
                <IconButton 
                  edge="end" 
                  onClick={(e) => {
                    e.stopPropagation();
                    setPreviewVideo({ id: video.id, filename: video.filename });
                    setPreviewDialogOpen(true);
                  }}
                  sx={{ mr: 1 }}
                  title="Preview Video"
                >
                  <PlayIcon />
                </IconButton>
                <IconButton 
                  edge="end" 
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditorVideo({ 
                      id: video.id, 
                      filename: video.filename,
                      url: apiClient.getVideoStreamUrl(projectId, video.id)
                    });
                  }}
                  title="Open Transcript Editor"
                >
                  <SubtitlesIcon />
                </IconButton>
                <IconButton
                  edge="end"
                  color="error"
                  onClick={() => {
                    if (confirm(`Delete "${video.filename}"?`)) {
                      deleteMutation.mutate(video.id);
                    }
                  }}
                >
                  <DeleteIcon />
                </IconButton>
              </ListItemSecondaryAction>
            </ListItem>
          ))}
        </List>
      )}

      {/* Upload Dialog */}
      <VideoUploadDialog
        open={uploadDialogOpen}
        onClose={() => setUploadDialogOpen(false)}
        onUpload={async (file, onProgress) => {
          await uploadMutation.mutateAsync({ file, onProgress });
        }}
        isUploading={uploadMutation.isPending}
      />

      {/* Video Preview Dialog */}
      {previewVideo && (
        <VideoPreviewDialog
          open={previewDialogOpen}
          onClose={() => {
            setPreviewDialogOpen(false);
            setPreviewVideo(null);
          }}
          videoUrl={apiClient.getVideoStreamUrl(projectId, previewVideo.id)}
          videoTitle={previewVideo.filename}
        />
      )}

      {/* Transcript Video Editor Dialog */}
      {editorVideo && (
        <Dialog
          open={!!editorVideo}
          onClose={() => setEditorVideo(null)}
          maxWidth="xl"
          fullWidth
          PaperProps={{
            sx: {
              height: '90vh',
              maxHeight: '90vh',
            },
          }}
        >
          <DialogTitle>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="h6">
                Transcript Editor - {editorVideo.filename}
              </Typography>
              <IconButton onClick={() => setEditorVideo(null)}>
                <CloseIcon />
              </IconButton>
            </Box>
          </DialogTitle>
          <DialogContent sx={{ p: 0, height: 'calc(100% - 80px)' }}>
            <TranscriptVideoEditor
              projectId={projectId}
              videoId={editorVideo.id}
              videoUrl={editorVideo.url}
              videoTitle={editorVideo.filename}
              style={{ height: '100%' }}
            />
          </DialogContent>
        </Dialog>
      )}
    </Box>
  );
}

