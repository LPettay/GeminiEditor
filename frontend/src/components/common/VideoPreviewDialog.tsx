/**
 * Video Preview Dialog - Uses modular video player components.
 * This can be easily swapped out with different UI implementations.
 */

import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  IconButton,
  Typography,
} from '@mui/material';
import {
  Close as CloseIcon,
} from '@mui/icons-material';
import { useState, useEffect } from 'react';
import { VideoPlayer } from './VideoPlayer';

interface VideoPreviewDialogProps {
  open: boolean;
  onClose: () => void;
  videoUrl: string;
  videoTitle: string;
}

export default function VideoPreviewDialog({
  open,
  onClose,
  videoUrl,
  videoTitle,
}: VideoPreviewDialogProps) {
  const [error, setError] = useState<string | null>(null);

  const handleClose = () => {
    setError(null);
    onClose();
  };

  const handleError = (errorMessage: string) => {
    setError(errorMessage);
  };

  // Reset error when dialog opens/closes
  useEffect(() => {
    if (!open) {
      setError(null);
    }
  }, [open]);

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="lg"
      fullWidth
      PaperProps={{
        sx: {
          bgcolor: 'background.paper',
          minHeight: '60vh',
        },
      }}
    >
      <DialogTitle>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="h6" noWrap>
            {videoTitle}
          </Typography>
          <IconButton onClick={handleClose}>
            <CloseIcon />
          </IconButton>
        </Box>
      </DialogTitle>

      <DialogContent sx={{ p: 0 }}>
        <VideoPlayer
          src={videoUrl}
          title={videoTitle}
          onError={handleError}
          style={{ height: '60vh' }}
        />
      </DialogContent>

      <DialogActions>
        <Button onClick={handleClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}