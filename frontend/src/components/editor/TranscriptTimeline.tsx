/**
 * Transcript Timeline - Main editing interface with draggable segments
 */

import { useState } from 'react';
import {
  Box,
  Typography,
  Button,
  ButtonGroup,
  IconButton,
  Collapse,
  Alert,
} from '@mui/material';
import {
  Undo as UndoIcon,
  Redo as RedoIcon,
  Save as SaveIcon,
  Visibility as ShowIcon,
  VisibilityOff as HideIcon,
  SelectAll as SelectAllIcon,
  Delete as DeleteIcon,
} from '@mui/icons-material';
import SegmentCard from './SegmentCard';
import { EditDecision } from '../../api/client';
import { useEditorStore } from '../../store/editorStore';

interface TranscriptTimelineProps {
  decisions: EditDecision[];
  currentClipIndex: number;
  onSave: () => Promise<void>;
  onEditDecision: (decisionId: string) => void;
}

export default function TranscriptTimeline({
  decisions,
  currentClipIndex,
  onSave,
  onEditDecision,
}: TranscriptTimelineProps) {
  const {
    selectedDecisions,
    showExcluded,
    toggleDecisionSelection,
    clearSelection,
    selectMultiple,
    setShowExcluded,
    toggleDecisionInclusion,
    removeDecision,
    undo,
    redo,
    canUndo,
    canRedo,
  } = useEditorStore();

  const [isSaving, setIsSaving] = useState(false);

  // Filter decisions based on showExcluded
  const visibleDecisions = showExcluded
    ? decisions
    : decisions.filter(d => d.is_included);

  const includedCount = decisions.filter(d => d.is_included).length;
  const excludedCount = decisions.length - includedCount;
  const selectedCount = selectedDecisions.length;

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onSave();
    } finally {
      setIsSaving(false);
    }
  };

  const handleSelectAll = () => {
    if (selectedCount === visibleDecisions.length) {
      clearSelection();
    } else {
      selectMultiple(visibleDecisions.map(d => d.id));
    }
  };

  const handleDeleteSelected = () => {
    if (confirm(`Delete ${selectedCount} selected segment(s)?`)) {
      selectedDecisions.forEach(id => removeDecision(id));
      clearSelection();
    }
  };

  const handleToggleInclusionSelected = () => {
    selectedDecisions.forEach(id => toggleDecisionInclusion(id));
  };

  // Keyboard shortcuts
  // TODO: Implement useEffect with keyboard event listeners

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Toolbar */}
      <Box
        sx={{
          p: 2,
          borderBottom: 1,
          borderColor: 'divider',
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          flexWrap: 'wrap',
        }}
      >
        {/* Undo/Redo */}
        <ButtonGroup variant="outlined" size="small">
          <IconButton onClick={undo} disabled={!canUndo()} title="Undo (Ctrl+Z)">
            <UndoIcon />
          </IconButton>
          <IconButton onClick={redo} disabled={!canRedo()} title="Redo (Ctrl+Shift+Z)">
            <RedoIcon />
          </IconButton>
        </ButtonGroup>

        {/* Selection Tools */}
        <ButtonGroup variant="outlined" size="small">
          <Button
            startIcon={<SelectAllIcon />}
            onClick={handleSelectAll}
          >
            {selectedCount === visibleDecisions.length ? 'Deselect All' : 'Select All'}
          </Button>
          {selectedCount > 0 && (
            <>
              <Button onClick={handleToggleInclusionSelected}>
                Toggle Inclusion ({selectedCount})
              </Button>
              <Button
                color="error"
                startIcon={<DeleteIcon />}
                onClick={handleDeleteSelected}
              >
                Delete ({selectedCount})
              </Button>
            </>
          )}
        </ButtonGroup>

        <Box sx={{ flexGrow: 1 }} />

        {/* Show/Hide Excluded */}
        <Button
          startIcon={showExcluded ? <HideIcon /> : <ShowIcon />}
          onClick={() => setShowExcluded(!showExcluded)}
          variant="outlined"
          size="small"
        >
          {showExcluded ? 'Hide' : 'Show'} Excluded ({excludedCount})
        </Button>

        {/* Save Button */}
        <Button
          variant="contained"
          startIcon={<SaveIcon />}
          onClick={handleSave}
          disabled={isSaving}
        >
          {isSaving ? 'Saving...' : 'Save Draft'}
        </Button>
      </Box>

      {/* Stats */}
      <Box sx={{ px: 2, py: 1, bgcolor: 'action.hover', display: 'flex', gap: 3 }}>
        <Typography variant="body2">
          <strong>Total:</strong> {decisions.length} segments
        </Typography>
        <Typography variant="body2" color="success.main">
          <strong>Included:</strong> {includedCount}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          <strong>Excluded:</strong> {excludedCount}
        </Typography>
        {selectedCount > 0 && (
          <Typography variant="body2" color="primary.main">
            <strong>Selected:</strong> {selectedCount}
          </Typography>
        )}
      </Box>

      {/* Segment List */}
      <Box
        sx={{
          flexGrow: 1,
          overflow: 'auto',
          p: 2,
        }}
      >
        {visibleDecisions.length === 0 ? (
          <Alert severity="info">
            {showExcluded
              ? 'No segments in this edit.'
              : 'No included segments. Toggle "Show Excluded" to see all segments.'}
          </Alert>
        ) : (
          visibleDecisions.map((decision, index) => (
            <SegmentCard
              key={decision.id}
              decision={decision}
              isSelected={selectedDecisions.includes(decision.id)}
              isCurrentlyPlaying={decision.order_index === currentClipIndex}
              onToggleSelection={toggleDecisionSelection}
              onToggleInclusion={toggleDecisionInclusion}
              onEdit={onEditDecision}
              onDelete={(id) => {
                if (confirm('Delete this segment?')) {
                  removeDecision(id);
                }
              }}
              // dragHandleProps will be added when we implement drag-and-drop
            />
          ))
        )}
      </Box>
    </Box>
  );
}

