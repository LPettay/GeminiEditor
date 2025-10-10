/**
 * Trim/Extend Modal - Fine-grained time controls for segment editing
 */

import { useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Box,
  Typography,
  Slider,
} from '@mui/material';
import { EditDecision } from '../../api/client';

interface TrimExtendModalProps {
  decision: EditDecision;
  onClose: () => void;
  onSave: (updates: { start_time: number; end_time: number }) => void;
}

export default function TrimExtendModal({ decision, onClose, onSave }: TrimExtendModalProps) {
  const [startTime, setStartTime] = useState(decision.start_time);
  const [endTime, setEndTime] = useState(decision.end_time);

  const duration = endTime - startTime;
  const originalDuration = decision.end_time - decision.start_time;

  const handleSave = () => {
    if (startTime >= endTime) {
      alert('Start time must be before end time');
      return;
    }
    if (duration < 0.1) {
      alert('Duration must be at least 0.1 seconds');
      return;
    }
    onSave({ start_time: startTime, end_time: endTime });
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(2);
    return `${mins}:${secs.padStart(5, '0')}`;
  };

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Edit Segment Timing</DialogTitle>
      <DialogContent>
        <Box sx={{ py: 2 }}>
          {/* Info */}
          <Typography variant="body2" color="text.secondary" gutterBottom>
            Segment #{decision.order_index + 1}
          </Typography>
          <Typography variant="body2" sx={{ mb: 3, fontStyle: 'italic' }}>
            "{decision.transcript_text.substring(0, 100)}
            {decision.transcript_text.length > 100 ? '...' : ''}"
          </Typography>

          {/* Start Time */}
          <Typography variant="subtitle2" gutterBottom>
            Start Time: {formatTime(startTime)}
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', mb: 3 }}>
            <Slider
              value={startTime}
              min={Math.max(0, decision.start_time - 5)}
              max={decision.end_time - 0.1}
              step={0.1}
              onChange={(_, value) => setStartTime(value as number)}
              sx={{ flexGrow: 1 }}
            />
            <TextField
              type="number"
              value={startTime.toFixed(2)}
              onChange={(e) => setStartTime(parseFloat(e.target.value))}
              inputProps={{ step: 0.1 }}
              sx={{ width: 100 }}
              size="small"
            />
          </Box>

          {/* End Time */}
          <Typography variant="subtitle2" gutterBottom>
            End Time: {formatTime(endTime)}
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', mb: 3 }}>
            <Slider
              value={endTime}
              min={decision.start_time + 0.1}
              max={decision.end_time + 5}
              step={0.1}
              onChange={(_, value) => setEndTime(value as number)}
              sx={{ flexGrow: 1 }}
            />
            <TextField
              type="number"
              value={endTime.toFixed(2)}
              onChange={(e) => setEndTime(parseFloat(e.target.value))}
              inputProps={{ step: 0.1 }}
              sx={{ width: 100 }}
              size="small"
            />
          </Box>

          {/* Duration Info */}
          <Box sx={{ bgcolor: 'action.hover', p: 2, borderRadius: 1 }}>
            <Typography variant="body2">
              <strong>Original Duration:</strong> {originalDuration.toFixed(2)}s
            </Typography>
            <Typography variant="body2">
              <strong>New Duration:</strong> {duration.toFixed(2)}s
            </Typography>
            <Typography
              variant="body2"
              color={duration > originalDuration ? 'success.main' : duration < originalDuration ? 'warning.main' : 'text.primary'}
            >
              <strong>Change:</strong> {duration > originalDuration ? '+' : ''}{(duration - originalDuration).toFixed(2)}s
            </Typography>
          </Box>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={() => {
          setStartTime(decision.start_time);
          setEndTime(decision.end_time);
        }}>
          Reset
        </Button>
        <Button onClick={handleSave} variant="contained">
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

