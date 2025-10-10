/**
 * Segment Card - Draggable card for a single transcript segment
 */

import { Box, Paper, Typography, IconButton, Checkbox, Chip } from '@mui/material';
import {
  DragIndicator as DragIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
} from '@mui/icons-material';
import { type EditDecision } from '../../api/client';

interface SegmentCardProps {
  decision: EditDecision;
  isSelected: boolean;
  isCurrentlyPlaying: boolean;
  onToggleSelection: (decisionId: string) => void;
  onToggleInclusion: (decisionId: string) => void;
  onEdit: (decisionId: string) => void;
  onDelete: (decisionId: string) => void;
  dragHandleProps?: any;
}

export default function SegmentCard({
  decision,
  isSelected,
  isCurrentlyPlaying,
  onToggleSelection,
  onToggleInclusion,
  onEdit,
  onDelete,
  dragHandleProps,
}: SegmentCardProps) {
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(1);
    return `${mins}:${secs.padStart(4, '0')}`;
  };

  const duration = decision.end_time - decision.start_time;

  return (
    <Paper
      sx={{
        p: 2,
        mb: 1,
        display: 'flex',
        alignItems: 'flex-start',
        gap: 2,
        opacity: decision.is_included ? 1 : 0.5,
        border: 2,
        borderColor: isCurrentlyPlaying ? 'primary.main' : 'transparent',
        bgcolor: isSelected ? 'action.selected' : 'background.paper',
        transition: 'all 0.2s',
        '&:hover': {
          boxShadow: 4,
        },
      }}
    >
      {/* Drag Handle */}
      <Box
        {...dragHandleProps}
        sx={{
          display: 'flex',
          alignItems: 'center',
          cursor: 'grab',
          '&:active': { cursor: 'grabbing' },
        }}
      >
        <DragIcon sx={{ color: 'text.secondary' }} />
      </Box>

      {/* Selection Checkbox */}
      <Checkbox
        checked={isSelected}
        onChange={() => onToggleSelection(decision.id)}
        sx={{ mt: -1 }}
      />

      {/* Content */}
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <Chip
            label={`#${decision.order_index + 1}`}
            size="small"
            color="primary"
            variant="outlined"
          />
          <Chip
            label={`${formatTime(decision.start_time)} - ${formatTime(decision.end_time)}`}
            size="small"
            variant="outlined"
          />
          <Chip
            label={`${duration.toFixed(1)}s`}
            size="small"
            variant="outlined"
          />
          {decision.is_ai_selected && (
            <Chip label="AI" size="small" color="primary" />
          )}
          {decision.user_modified && (
            <Chip label="Modified" size="small" color="secondary" />
          )}
        </Box>

        {/* Transcript Text */}
        <Typography
          variant="body2"
          sx={{
            color: decision.is_included ? 'text.primary' : 'text.disabled',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {decision.transcript_text}
        </Typography>
      </Box>

      {/* Actions */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        <IconButton
          size="small"
          onClick={() => onToggleInclusion(decision.id)}
          color={decision.is_included ? 'success' : 'default'}
          title={decision.is_included ? 'Exclude' : 'Include'}
        >
          <Checkbox checked={decision.is_included} size="small" />
        </IconButton>
        <IconButton
          size="small"
          onClick={() => onEdit(decision.id)}
          title="Edit times"
        >
          <EditIcon fontSize="small" />
        </IconButton>
        <IconButton
          size="small"
          color="error"
          onClick={() => onDelete(decision.id)}
          title="Delete"
        >
          <DeleteIcon fontSize="small" />
        </IconButton>
      </Box>
    </Paper>
  );
}

