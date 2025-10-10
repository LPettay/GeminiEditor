import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query';
import axios from 'axios';
import UploadForm from './components/UploadForm';
import type { UploadFormValues } from './components/UploadForm';
import { Container, CssBaseline, Snackbar, Alert, ThemeProvider, createTheme } from '@mui/material';
import { useState } from 'react';

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
  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string; severity: 'success' | 'error' }>({
    open: false,
    message: '',
    severity: 'success',
  });

  const processVideo = async (data: UploadFormValues) => {
    const formData = new FormData();
    if (data.fileId) {
      formData.append('file_id', data.fileId);
    } else {
      formData.append('file', data.video[0]);
    }
    if (data.scopeStart !== undefined) formData.append('scope_start_seconds', String(data.scopeStart));
    if (data.scopeEnd !== undefined) formData.append('scope_end_seconds', String(data.scopeEnd));
    if (data.audioTrack !== undefined) formData.append('audio_track', String(data.audioTrack - 1));
    if (data.prompt) formData.append('prompt', data.prompt);
    if (data.enableVisionExtension !== undefined) formData.append('enable_vision_extension', String(data.enableVisionExtension));
    if (data.enableMultimodalPass2 !== undefined) formData.append('enable_multimodal_pass2', String(data.enableMultimodalPass2));
    if (data.simpleMode !== undefined) formData.append('simple_mode', String(data.simpleMode));
    const response = await axios.post('/process', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  };

  const mutation = useMutation({
    mutationFn: processVideo,
    onSuccess: () => setSnackbar({ open: true, message: 'Processing started successfully', severity: 'success' }),
    onError: (err: any) => setSnackbar({ open: true, message: err.message ?? 'Error', severity: 'error' }),
  });

  return (
    <ThemeProvider theme={darkTheme}>
      <QueryClientProvider client={queryClient}>
        <CssBaseline />
        <Container 
          disableGutters
          sx={{ 
            py: 4,
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center'
          }}
        >
          <UploadForm onSubmit={(values) => mutation.mutate(values)} isSubmitting={mutation.isPending} />
        </Container>
        <Snackbar
          open={snackbar.open}
          autoHideDuration={4000}
          onClose={() => setSnackbar((s) => ({ ...s, open: false }))}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
          <Alert severity={snackbar.severity} variant="filled" sx={{ width: '100%' }}>
            {snackbar.message}
          </Alert>
        </Snackbar>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

export default App;
