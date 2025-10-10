/**
 * Transcript Display - Shows transcript with live word highlighting.
 * This component can be easily swapped out with different transcript UI implementations.
 */

import React, { useEffect, useState, useRef } from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  LinearProgress,
} from '@mui/material';
import {
  Sync as SyncIcon,
  VolumeUp as VolumeUpIcon,
} from '@mui/icons-material';
import { TranscriptSegment, TranscriptWord, SyncState } from '../../services/transcriptSyncService';

export interface TranscriptDisplayProps {
  segments: TranscriptSegment[];
  currentSegmentId?: string | null;
  currentWordIndex?: number;
  onSegmentClick?: (segment: TranscriptSegment) => void;
  onWordClick?: (word: TranscriptWord, segment: TranscriptSegment) => void;
  showSpeakers?: boolean;
  showConfidence?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

export const TranscriptDisplay: React.FC<TranscriptDisplayProps> = ({
  segments,
  currentSegmentId,
  currentWordIndex = -1,
  onSegmentClick,
  onWordClick,
  showSpeakers = true,
  showConfidence = false,
  className,
  style,
}) => {
  const segmentRefs = useRef<{ [key: string]: HTMLDivElement | null }>({});
  const [expandedSegments, setExpandedSegments] = useState<Set<string>>(new Set());

  // Auto-scroll to current segment
  useEffect(() => {
    if (currentSegmentId && segmentRefs.current[currentSegmentId]) {
      segmentRefs.current[currentSegmentId]?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [currentSegmentId]);

  const formatTime = (time: number): string => {
    const minutes = Math.floor(time / 60);
    const seconds = Math.floor(time % 60);
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  };

  const getWordStyle = (
    word: TranscriptWord,
    segment: TranscriptSegment,
    wordIndex: number
  ): React.CSSProperties => {
    const isCurrentWord = 
      segment.id === currentSegmentId && 
      wordIndex === currentWordIndex;
    
    const isCurrentSegment = segment.id === currentSegmentId;
    
    return {
      display: 'inline',
      margin: '0 1px',
      padding: '1px 2px',
      borderRadius: '3px',
      backgroundColor: isCurrentWord 
        ? 'rgba(144, 202, 249, 0.8)' 
        : isCurrentSegment 
        ? 'rgba(144, 202, 249, 0.3)' 
        : 'transparent',
      cursor: onWordClick ? 'pointer' : 'default',
      transition: 'background-color 0.2s ease',
      fontWeight: isCurrentWord ? 'bold' : 'normal',
      color: isCurrentWord ? '#1976d2' : '#333333', // Ensure text is visible
    };
  };

  const getSegmentStyle = (segment: TranscriptSegment): React.CSSProperties => {
    const isCurrent = segment.id === currentSegmentId;
    return {
      border: isCurrent ? '2px solid #90caf9' : '1px solid #e0e0e0',
      borderRadius: '8px',
      padding: '12px',
      margin: '8px 0',
      backgroundColor: isCurrent ? 'rgba(144, 202, 249, 0.1)' : 'white',
      cursor: onSegmentClick ? 'pointer' : 'default',
      transition: 'all 0.2s ease',
    };
  };

  const handleSegmentClick = (segment: TranscriptSegment) => {
    onSegmentClick?.(segment);
  };

  const handleWordClick = (word: TranscriptWord, segment: TranscriptSegment) => {
    onWordClick?.(word, segment);
  };

  const toggleSegmentExpansion = (segmentId: string) => {
    setExpandedSegments(prev => {
      const newSet = new Set(prev);
      if (newSet.has(segmentId)) {
        newSet.delete(segmentId);
      } else {
        newSet.add(segmentId);
      }
      return newSet;
    });
  };

  if (segments.length === 0) {
    return (
      <Box 
        className={className}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '200px',
          ...style,
        }}
      >
        <Typography variant="body2" color="text.secondary">
          No transcript available
        </Typography>
      </Box>
    );
  }

  return (
    <Box 
      className={className}
      style={{
        height: '100%',
        overflow: 'auto',
        padding: '16px',
        ...style,
      }}
    >
      {segments.map((segment) => {
        const isExpanded = expandedSegments.has(segment.id);
        const isCurrent = segment.id === currentSegmentId;
        
        return (
          <Paper
            key={segment.id}
            ref={(el) => (segmentRefs.current[segment.id] = el)}
            style={getSegmentStyle(segment)}
            onClick={() => handleSegmentClick(segment)}
          >
            {/* Segment Header */}
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
              <Typography variant="caption" color="text.secondary" sx={{ mr: 2 }}>
                {formatTime(segment.start)} - {formatTime(segment.end)}
              </Typography>
              
              {showSpeakers && segment.speaker && (
                <Chip
                  label={segment.speaker}
                  size="small"
                  sx={{ mr: 1 }}
                />
              )}
              
              {showConfidence && (
                <Chip
                  label={`${Math.round(segment.confidence * 100)}%`}
                  size="small"
                  color={segment.confidence > 0.8 ? 'success' : 'warning'}
                  sx={{ mr: 1 }}
                />
              )}
              
              {isCurrent && (
                <Chip
                  icon={<SyncIcon />}
                  label="Playing"
                  size="small"
                  color="primary"
                />
              )}
            </Box>

            {/* Progress bar for current segment */}
            {isCurrent && segment.words && segment.words.length > 0 && (
              <LinearProgress
                variant="determinate"
                value={((currentWordIndex + 1) / segment.words.length) * 100}
                sx={{ mb: 1, height: 4, borderRadius: 2 }}
              />
            )}

            {/* Segment Text */}
            <Box sx={{ mb: 1 }}>
              {segment.words && segment.words.length > 0 ? (
                // Word-level display with highlighting
                (segment.words || []).map((word, wordIndex) => (
                  <span
                    key={wordIndex}
                    style={getWordStyle(word, segment, wordIndex)}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleWordClick(word, segment);
                    }}
                    title={`${word.word} (${formatTime(word.start)} - ${formatTime(word.end)})`}
                  >
                    {word.word}
                  </span>
                ))
              ) : (
                // Fallback to segment text if no word-level data
                <Typography variant="body1" style={{ lineHeight: 1.6, color: '#333333' }}>
                  {segment.text}
                </Typography>
              )}
            </Box>

            {/* Expandable detailed view */}
            {isExpanded && (
              <Box sx={{ mt: 2, p: 2, bgcolor: 'rgba(0, 0, 0, 0.02)', borderRadius: 1 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Word-level timestamps:
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {(segment.words || []).map((word, wordIndex) => (
                    <Chip
                      key={wordIndex}
                      label={`${word.word} (${formatTime(word.start)})`}
                      size="small"
                      variant="outlined"
                      style={getWordStyle(word, segment, wordIndex)}
                    />
                  ))}
                </Box>
              </Box>
            )}
          </Paper>
        );
      })}
    </Box>
  );
};
