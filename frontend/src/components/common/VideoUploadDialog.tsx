/**
 * Video Upload Dialog Component
 */

import { useState, useRef } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  LinearProgress,
  Alert,
  IconButton,
} from '@mui/material';
import {
  CloudUpload as UploadIcon,
  Close as CloseIcon,
} from '@mui/icons-material';

interface VideoUploadDialogProps {
  open: boolean;
  onClose: () => void;
  onUpload: (file: File, onProgress: (progress: number) => void) => Promise<void>;
  isUploading: boolean;
}

export default function VideoUploadDialog({
  open,
  onClose,
  onUpload,
  isUploading,
}: VideoUploadDialogProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (file: File) => {
    // Validate file type
    if (!file.type.startsWith('video/')) {
      setError('Please select a video file');
      return;
    }

    // Validate file size (15GB limit)
    const maxSize = 15 * 1024 * 1024 * 1024; // 15GB
    if (file.size > maxSize) {
      setError('File size must be less than 15GB');
      return;
    }

    setSelectedFile(file);
    setError(null);
  };

  const handleFileInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      handleFileSelect(file);
    }
  };

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    setDragActive(false);
    
    const file = event.dataTransfer.files[0];
    if (file) {
      handleFileSelect(file);
    }
  };

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault();
    setDragActive(true);
  };

  const handleDragLeave = (event: React.DragEvent) => {
    event.preventDefault();
    setDragActive(false);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    try {
      setError(null);
      await onUpload(selectedFile, setUploadProgress);
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    }
  };

  const handleClose = () => {
    setSelectedFile(null);
    setUploadProgress(0);
    setError(null);
    setDragActive(false);
    onClose();
  };

  const formatFileSize = (bytes: number) => {
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(2)} MB`;
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
      disableEnforceFocus={false}
      disableAutoFocus={false}
      disableRestoreFocus={false}
    >
      <DialogTitle>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          Upload Video
          <IconButton onClick={handleClose} disabled={isUploading}>
            <CloseIcon />
          </IconButton>
        </Box>
      </DialogTitle>
      
      <DialogContent>
        <Box
          sx={{
            border: 2,
            borderColor: dragActive ? 'primary.main' : 'divider',
            borderStyle: 'dashed',
            borderRadius: 2,
            p: 4,
            textAlign: 'center',
            bgcolor: dragActive ? 'action.hover' : 'background.paper',
            transition: 'all 0.2s ease',
            cursor: 'pointer',
            mb: 2,
          }}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
        >
          <UploadIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
          <Typography variant="h6" gutterBottom>
            {dragActive ? 'Drop video here' : 'Drag & drop video or click to select'}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Supports MP4, MOV, AVI, and other video formats (max 15GB)
          </Typography>
        </Box>

        <input
          ref={fileInputRef}
          type="file"
          accept="video/*"
          onChange={handleFileInputChange}
          style={{ display: 'none' }}
        />

        {selectedFile && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Selected File:
            </Typography>
            <Typography variant="body2">
              {selectedFile.name} ({formatFileSize(selectedFile.size)})
            </Typography>
          </Box>
        )}

        {isUploading && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" gutterBottom>
              Uploading... {uploadProgress}%
            </Typography>
            <LinearProgress variant="determinate" value={uploadProgress} />
          </Box>
        )}

        {error && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {error}
          </Alert>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={handleClose} disabled={isUploading}>
          Cancel
        </Button>
        <Button
          onClick={handleUpload}
          variant="contained"
          disabled={!selectedFile || isUploading}
        >
          {isUploading ? 'Uploading...' : 'Upload'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
