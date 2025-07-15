import { useState } from 'react';
import { Box, Button, Typography, Paper, Collapse } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';

interface DebugPanelProps {
  title: string;
  data: Record<string, any>;
  defaultOpen?: boolean;
}

const DebugPanel: React.FC<DebugPanelProps> = ({ title, data, defaultOpen = false }) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <Paper sx={{ p: 1, mb: 1, backgroundColor: '#f5f5f5' }}>
      <Button
        onClick={() => setIsOpen(!isOpen)}
        startIcon={isOpen ? <ExpandLessIcon /> : <ExpandMoreIcon />}
        size="small"
        sx={{ textTransform: 'none' }}
      >
        {title}
      </Button>
      <Collapse in={isOpen}>
        <Box sx={{ mt: 1, fontFamily: 'monospace', fontSize: '0.8rem' }}>
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(data, null, 2)}
          </pre>
        </Box>
      </Collapse>
    </Paper>
  );
};

export default DebugPanel; 