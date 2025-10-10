/**
 * Project Detail Page - Shows source videos, edits, and settings
 */

import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Box,
  Typography,
  Tabs,
  Tab,
  CircularProgress,
  Alert,
  IconButton,
} from '@mui/material';
import { ArrowBack as ArrowBackIcon } from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';
import { useProjectStore } from '../store/projectStore';

// Tab panels
import SourceVideosTab from '../components/project/SourceVideosTab';
import EditsTab from '../components/project/EditsTab';
import SettingsTab from '../components/project/SettingsTab';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`project-tabpanel-${index}`}
      aria-labelledby={`project-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );
}

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { setCurrentProject, currentProject } = useProjectStore();
  const [currentTab, setCurrentTab] = useState(0);

  // Fetch project details
  const { isLoading, error } = useQuery({
    queryKey: ['project', projectId],
    queryFn: async () => {
      const data = await apiClient.getProject(projectId!);
      setCurrentProject(data);
      return data;
    },
    enabled: !!projectId,
  });

  if (isLoading) {
    return (
      <Container sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <CircularProgress />
      </Container>
    );
  }

  if (error || !currentProject) {
    return (
      <Container sx={{ py: 4 }}>
        <Alert severity="error">
          Failed to load project: {error?.toString() || 'Unknown error'}
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 3, display: 'flex', alignItems: 'center', gap: 2 }}>
        <IconButton onClick={() => navigate('/projects')} size="large">
          <ArrowBackIcon />
        </IconButton>
        <Box>
          <Typography variant="h4" component="h1">
            {currentProject.name}
          </Typography>
          {currentProject.description && (
            <Typography variant="body2" color="text.secondary">
              {currentProject.description}
            </Typography>
          )}
        </Box>
      </Box>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs value={currentTab} onChange={(_, newValue) => setCurrentTab(newValue)}>
          <Tab label="Source Videos" />
          <Tab label="Edits" />
          <Tab label="Settings" />
        </Tabs>
      </Box>

      {/* Tab Panels */}
      <TabPanel value={currentTab} index={0}>
        <SourceVideosTab projectId={projectId!} />
      </TabPanel>
      <TabPanel value={currentTab} index={1}>
        <EditsTab projectId={projectId!} />
      </TabPanel>
      <TabPanel value={currentTab} index={2}>
        <SettingsTab project={currentProject} />
      </TabPanel>
    </Container>
  );
}

