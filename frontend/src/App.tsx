import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query';
import axios from 'axios';
import UploadForm from './components/UploadForm';
import type { UploadFormValues } from './components/UploadForm';
import { Container, CssBaseline, Snackbar, Alert } from '@mui/material';
import { useState } from 'react';

const queryClient = new QueryClient();

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
    if (data.audioTrack !== undefined) formData.append('audio_track', String(data.audioTrack));
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
    <QueryClientProvider client={queryClient}>
      <CssBaseline />
      <Container maxWidth="md" sx={{ py: 4 }}>
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
  );
}

export default App;
