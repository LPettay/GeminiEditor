/**
 * Legacy Upload Page - Wraps the original upload form
 */

import { Container, Box, Typography, Alert } from '@mui/material';
import UploadForm from '../components/UploadForm';

export default function LegacyUploadPage() {
  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Alert severity="info" sx={{ mb: 3 }}>
        This is the legacy upload interface. For the new project-based workflow, go to Projects.
      </Alert>
      
      <Box>
        <Typography variant="h4" gutterBottom>
          Legacy Video Upload
        </Typography>
        <UploadForm
          onSubmit={(values) => {
            console.log('Legacy upload:', values);
          }}
          isSubmitting={false}
        />
      </Box>
    </Container>
  );
}

