/**
 * Project List Page - Grid view of all projects
 */

import { useState, useRef, useEffect } from 'react';
import {
  Container,
  Box,
  Typography,
  Button,
  Grid,
  Card,
  CardContent,
  CardActions,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  CircularProgress,
  Alert,
} from '@mui/material';
import {
  Add as AddIcon,
  Settings as SettingsIcon,
  Delete as DeleteIcon,
  Folder as FolderIcon,
} from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';
import { useProjectStore } from '../store/projectStore';
import { useNavigate } from 'react-router-dom';

export default function ProjectListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { setProjects, projects, setError } = useProjectStore();
  
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDescription, setNewProjectDescription] = useState('');
  const nameInputRef = useRef<HTMLInputElement>(null);

  // Focus management for dialog
  useEffect(() => {
    if (createDialogOpen && nameInputRef.current) {
      // Small delay to ensure dialog is fully rendered
      setTimeout(() => {
        nameInputRef.current?.focus();
      }, 100);
    }
  }, [createDialogOpen]);

  // Fetch projects
  const { isLoading, error } = useQuery({
    queryKey: ['projects'],
    queryFn: async () => {
      const data = await apiClient.getProjects();
      setProjects(data);
      return data;
    },
  });

  // Create project mutation
  const createMutation = useMutation({
    mutationFn: (data: { name: string; description?: string }) =>
      apiClient.createProject(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      setCreateDialogOpen(false);
      setNewProjectName('');
      setNewProjectDescription('');
    },
    onError: (err: any) => {
      setError(err.message || 'Failed to create project');
    },
  });

  // Delete project mutation
  const deleteMutation = useMutation({
    mutationFn: (projectId: string) => apiClient.deleteProject(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
    onError: (err: any) => {
      setError(err.message || 'Failed to delete project');
    },
  });

  const handleCreateProject = () => {
    if (newProjectName.trim()) {
      createMutation.mutate({
        name: newProjectName,
        description: newProjectDescription || undefined,
      });
    }
  };

  const handleDeleteProject = (projectId: string, projectName: string) => {
    if (confirm(`Are you sure you want to delete "${projectName}"? This will delete all associated videos and edits.`)) {
      deleteMutation.mutate(projectId);
    }
  };

  if (isLoading) {
    return (
      <Container sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <CircularProgress />
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h3" component="h1">
          Projects
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreateDialogOpen(true)}
          size="large"
        >
          New Project
        </Button>
      </Box>

      {/* Error display */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error instanceof Error ? error.message : String(error)}
        </Alert>
      )}

      {/* Project grid */}
      {projects.length === 0 ? (
        <Box sx={{ textAlign: 'center', py: 8 }}>
          <FolderIcon sx={{ fontSize: 80, color: 'text.secondary', mb: 2 }} />
          <Typography variant="h5" color="text.secondary" gutterBottom>
            No projects yet
          </Typography>
          <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
            Create your first project to get started
          </Typography>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setCreateDialogOpen(true)}
          >
            Create Project
          </Button>
        </Box>
      ) : (
        <Grid container spacing={3}>
          {projects.map((project) => (
            <Grid size={{ xs: 12, sm: 6, md: 4, lg: 3 }} key={project.id}>
              <Card
                sx={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  '&:hover': {
                    boxShadow: 6,
                    cursor: 'pointer',
                  },
                }}
                onClick={() => navigate(`/projects/${project.id}`)}
              >
                <CardContent sx={{ flexGrow: 1 }}>
                  <Typography variant="h6" gutterBottom noWrap>
                    {project.name}
                  </Typography>
                  {project.description && (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        display: '-webkit-box',
                        WebkitLineClamp: 3,
                        WebkitBoxOrient: 'vertical',
                      }}
                    >
                      {project.description}
                    </Typography>
                  )}
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                    Updated: {new Date(project.updated_at).toLocaleDateString()}
                  </Typography>
                </CardContent>
                <CardActions>
                  <IconButton
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/projects/${project.id}`);
                    }}
                  >
                    <SettingsIcon />
                  </IconButton>
                  <IconButton
                    size="small"
                    color="error"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteProject(project.id, project.name);
                    }}
                  >
                    <DeleteIcon />
                  </IconButton>
                </CardActions>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      {/* Create Project Dialog */}
      <Dialog
        open={createDialogOpen}
        onClose={() => setCreateDialogOpen(false)}
        maxWidth="sm"
        fullWidth
        disableEnforceFocus={false}
        disableAutoFocus={false}
        disableRestoreFocus={false}
        keepMounted={false}
      >
        <DialogTitle>Create New Project</DialogTitle>
        <DialogContent>
          <TextField
            ref={nameInputRef}
            autoFocus
            margin="dense"
            label="Project Name"
            fullWidth
            variant="outlined"
            value={newProjectName}
            onChange={(e) => setNewProjectName(e.target.value)}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Description (optional)"
            fullWidth
            variant="outlined"
            multiline
            rows={3}
            value={newProjectDescription}
            onChange={(e) => setNewProjectDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleCreateProject}
            variant="contained"
            disabled={!newProjectName.trim() || createMutation.isPending}
          >
            {createMutation.isPending ? 'Creating...' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}

