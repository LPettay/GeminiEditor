/**
 * Edits Tab - Shows and manages edits for a project
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
  Menu,
  MenuItem,
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  FileCopy as DuplicateIcon,
  Download as DownloadIcon,
  MoreVert as MoreIcon,
  CheckCircle as CheckCircleIcon,
} from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import apiClient from '../../api/client';

interface EditsTabProps {
  projectId: string;
}

export default function EditsTab({ projectId }: EditsTabProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [menuAnchor, setMenuAnchor] = useState<{ element: HTMLElement; editId: string } | null>(null);

  // Fetch edits
  const { data: edits, isLoading, error } = useQuery({
    queryKey: ['edits', projectId],
    queryFn: () => apiClient.getEdits(projectId),
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (editId: string) => apiClient.deleteEdit(projectId, editId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['edits', projectId] });
    },
  });

  // Duplicate mutation
  const duplicateMutation = useMutation({
    mutationFn: ({ editId, newName }: { editId: string; newName?: string }) =>
      apiClient.duplicateEdit(projectId, editId, newName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['edits', projectId] });
      setMenuAnchor(null);
    },
  });

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>, editId: string) => {
    setMenuAnchor({ element: event.currentTarget, editId });
  };

  const handleMenuClose = () => {
    setMenuAnchor(null);
  };

  const handleDuplicate = () => {
    if (menuAnchor) {
      duplicateMutation.mutate({ editId: menuAnchor.editId });
    }
  };

  const handleDelete = (editId: string, editName: string) => {
    if (confirm(`Delete edit "${editName}"?`)) {
      deleteMutation.mutate(editId);
    }
  };

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">Failed to load edits</Alert>;
  }

  return (
    <Box>
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h6">Edits</Typography>
        <Button variant="contained" startIcon={<AddIcon />} disabled>
          New Edit (Coming Soon)
        </Button>
      </Box>

      {!edits || edits.length === 0 ? (
        <Alert severity="info">
          No edits yet. Create an edit from a source video to get started.
        </Alert>
      ) : (
        <List>
          {edits.map((edit) => (
            <ListItem
              key={edit.id}
              sx={{
                border: 1,
                borderColor: 'divider',
                borderRadius: 1,
                mb: 1,
                '&:hover': { bgcolor: 'action.hover', cursor: 'pointer' },
              }}
              onClick={() => navigate(`/projects/${projectId}/edits/${edit.id}`)}
            >
              <ListItemText
                primary={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {edit.name}
                    {edit.is_finalized && (
                      <CheckCircleIcon color="success" fontSize="small" />
                    )}
                  </Box>
                }
                secondary={
                  <Box sx={{ mt: 1 }}>
                    <Chip label={`v${edit.version}`} size="small" sx={{ mr: 1 }} />
                    {edit.is_finalized ? (
                      <Chip label="Finalized" color="success" size="small" sx={{ mr: 1 }} />
                    ) : (
                      <Chip label="Draft" color="default" size="small" sx={{ mr: 1 }} />
                    )}
                    {edit.ai_processing_complete && (
                      <Chip label="AI Processed" color="primary" size="small" />
                    )}
                    <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                      Updated: {new Date(edit.updated_at).toLocaleString()}
                    </Typography>
                  </Box>
                }
              />
              <ListItemSecondaryAction>
                {edit.is_finalized && (
                  <IconButton
                    edge="end"
                    sx={{ mr: 1 }}
                    onClick={(e) => {
                      e.stopPropagation();
                      window.location.href = apiClient.getDownloadUrl(projectId, edit.id);
                    }}
                  >
                    <DownloadIcon />
                  </IconButton>
                )}
                <IconButton
                  edge="end"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleMenuOpen(e, edit.id);
                  }}
                >
                  <MoreIcon />
                </IconButton>
              </ListItemSecondaryAction>
            </ListItem>
          ))}
        </List>
      )}

      {/* Context Menu */}
      <Menu
        anchorEl={menuAnchor?.element}
        open={Boolean(menuAnchor)}
        onClose={handleMenuClose}
      >
        <MenuItem
          onClick={() => {
            if (menuAnchor) {
              navigate(`/projects/${projectId}/edits/${menuAnchor.editId}`);
            }
          }}
        >
          <EditIcon fontSize="small" sx={{ mr: 1 }} />
          Open Editor
        </MenuItem>
        <MenuItem onClick={handleDuplicate} disabled={duplicateMutation.isPending}>
          <DuplicateIcon fontSize="small" sx={{ mr: 1 }} />
          Duplicate
        </MenuItem>
        <MenuItem
          onClick={() => {
            if (menuAnchor) {
              const edit = edits?.find((e) => e.id === menuAnchor.editId);
              if (edit) {
                handleDelete(edit.id, edit.name);
                handleMenuClose();
              }
            }
          }}
          sx={{ color: 'error.main' }}
        >
          <DeleteIcon fontSize="small" sx={{ mr: 1 }} />
          Delete
        </MenuItem>
      </Menu>
    </Box>
  );
}

