/**
 * Settings Tab - Project settings and metadata
 */

import { useState } from 'react';
import {
  Box,
  TextField,
  Button,
  Typography,
  Alert,
  Divider,
} from '@mui/material';
import { Save as SaveIcon } from '@mui/icons-material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient, { Project } from '../../api/client';

interface SettingsTabProps {
  project: Project;
}

export default function SettingsTab({ project }: SettingsTabProps) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description || '');
  const [successMessage, setSuccessMessage] = useState('');

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: { name?: string; description?: string }) =>
      apiClient.updateProject(project.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', project.id] });
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      setSuccessMessage('Settings saved successfully!');
      setTimeout(() => setSuccessMessage(''), 3000);
    },
  });

  const handleSave = () => {
    updateMutation.mutate({
      name: name !== project.name ? name : undefined,
      description: description !== project.description ? description : undefined,
    });
  };

  const hasChanges = name !== project.name || description !== (project.description || '');

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Project Settings
      </Typography>

      {successMessage && (
        <Alert severity="success" sx={{ mb: 3 }}>
          {successMessage}
        </Alert>
      )}

      <Box sx={{ maxWidth: 600 }}>
        <TextField
          fullWidth
          label="Project Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          margin="normal"
          required
        />

        <TextField
          fullWidth
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          margin="normal"
          multiline
          rows={4}
        />

        <Button
          variant="contained"
          startIcon={<SaveIcon />}
          onClick={handleSave}
          disabled={!hasChanges || !name.trim() || updateMutation.isPending}
          sx={{ mt: 2 }}
        >
          {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
        </Button>

        <Divider sx={{ my: 4 }} />

        <Typography variant="h6" gutterBottom>
          Project Information
        </Typography>

        <Box sx={{ mt: 2 }}>
          <Typography variant="body2" color="text.secondary">
            <strong>Project ID:</strong> {project.id}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            <strong>Created:</strong> {new Date(project.created_at).toLocaleString()}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            <strong>Last Updated:</strong> {new Date(project.updated_at).toLocaleString()}
          </Typography>
        </Box>

        <Divider sx={{ my: 4 }} />

        <Typography variant="h6" gutterBottom color="error">
          Danger Zone
        </Typography>

        <Alert severity="warning" sx={{ mb: 2 }}>
          Deleting a project will permanently remove all source videos, transcripts, edits, and
          associated data. This action cannot be undone.
        </Alert>

        <Button variant="outlined" color="error" disabled>
          Delete Project (Coming Soon)
        </Button>
      </Box>
    </Box>
  );
}

