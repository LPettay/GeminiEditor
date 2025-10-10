/**
 * Main application component with routing.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';

// Pages
import ProjectListPage from './pages/ProjectListPage';
import ProjectDetailPage from './pages/ProjectDetailPage';
import EditEditorPage from './pages/EditEditorPage';
import LegacyUploadPage from './pages/LegacyUploadPage';

const queryClient = new QueryClient();

// Create a dark theme
const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    background: {
      default: '#121212',
      paper: '#1e1e1e',
    },
    primary: {
      main: '#90caf9',
    },
    secondary: {
      main: '#f48fb1',
    },
  },
});

function App() {
  return (
    <ThemeProvider theme={darkTheme}>
      <QueryClientProvider client={queryClient}>
        <CssBaseline />
        <BrowserRouter>
          <Routes>
            {/* Redirect root to projects */}
            <Route path="/" element={<Navigate to="/projects" replace />} />
            
            {/* Project routes */}
            <Route path="/projects" element={<ProjectListPage />} />
            <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
            
            {/* Edit editor route */}
            <Route path="/projects/:projectId/edits/:editId" element={<EditEditorPage />} />
            
            {/* Legacy upload page (for backward compatibility) */}
            <Route path="/legacy-upload" element={<LegacyUploadPage />} />
            
            {/* 404 fallback */}
            <Route path="*" element={<Navigate to="/projects" replace />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

export default App;

