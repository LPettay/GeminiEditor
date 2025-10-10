/**
 * Reorderable Transcript - Drag & drop interface for rearranging transcript segments.
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  LinearProgress,
  IconButton,
  Alert,
  Button,
} from '@mui/material';
import {
  DragIndicator as DragIcon,
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  AutoAwesome as ProcessIcon,
} from '@mui/icons-material';
import {
  DragDropContext,
  Droppable,
  Draggable,
  DropResult,
} from '@hello-pangea/dnd';
import { TranscriptSegment, TranscriptWord } from '../../services/transcriptSyncService';

export interface ReorderableTranscriptProps {
  segments: TranscriptSegment[];
  currentSegmentId?: string | null;
  currentWordIndex?: number;
  onSegmentsReorder: (reorderedSegments: TranscriptSegment[]) => void;
  onSegmentClick?: (segment: TranscriptSegment) => void;
  onWordClick?: (word: TranscriptWord, segment: TranscriptSegment) => void;
  onSegmentVideo?: (segment: TranscriptSegment) => void;
  showSpeakers?: boolean;
  showConfidence?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

interface SegmentWithOrder extends TranscriptSegment {
  orderIndex: number;
}

export const ReorderableTranscript: React.FC<ReorderableTranscriptProps> = ({
  segments,
  currentSegmentId,
  currentWordIndex = -1,
  onSegmentsReorder,
  onSegmentClick,
  onWordClick,
  onSegmentVideo,
  showSpeakers = true,
  showConfidence = false,
  className,
  style,
}) => {
  const [segmentsWithOrder, setSegmentsWithOrder] = useState<SegmentWithOrder[]>(() =>
    segments.map((segment, index) => ({
      ...segment,
      orderIndex: index,
    }))
  );
  const [scrollOffset, setScrollOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const autoScrollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Track scroll position for drag alignment
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleScroll = () => {
      setScrollOffset({
        x: container.scrollLeft,
        y: container.scrollTop,
      });
    };

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  // Simple scroll tracking - let the library handle positioning
  // The ignoreContainerClipping prop should help with scroll issues

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
      color: isCurrentWord ? '#1976d2' : '#333333',
    };
  };

  const getSegmentStyle = (segment: TranscriptSegment, isDragging: boolean = false): React.CSSProperties => {
    const isCurrent = segment.id === currentSegmentId;
    return {
      border: isCurrent ? '2px solid #90caf9' : '1px solid #e0e0e0',
      borderRadius: '8px',
      padding: '12px',
      margin: '8px 0',
      backgroundColor: isCurrent ? 'rgba(144, 202, 249, 0.1)' : 'white',
      cursor: onSegmentClick ? 'pointer' : 'default',
      transition: 'all 0.2s ease',
      position: 'relative',
      // Only apply drag styles when not dragging (let library handle drag state)
      ...(isDragging ? {} : {
        boxShadow: isCurrent 
          ? '0 2px 8px rgba(144, 202, 249, 0.3)' 
          : '0 1px 3px rgba(0,0,0,0.1)',
      }),
    };
  };

  const handleDragStart = () => {
    setIsDragging(true);
  };

  const handleDragEnd = (result: DropResult) => {
    setIsDragging(false);
    
    if (!result.destination) return;

    const newSegments = Array.from(segmentsWithOrder);
    const [reorderedItem] = newSegments.splice(result.source.index, 1);
    newSegments.splice(result.destination.index, 0, reorderedItem);

    // Update order indices
    const updatedSegments = newSegments.map((segment, index) => ({
      ...segment,
      orderIndex: index,
    }));

    setSegmentsWithOrder(updatedSegments);
    
    // Notify parent component
    onSegmentsReorder(updatedSegments);
  };

  const handleSegmentClick = (segment: TranscriptSegment) => {
    onSegmentClick?.(segment);
  };

  const handleWordClick = (word: TranscriptWord, segment: TranscriptSegment) => {
    onWordClick?.(word, segment);
  };

  const handleSegmentVideo = (segment: TranscriptSegment) => {
    onSegmentVideo?.(segment);
  };

  if (segmentsWithOrder.length === 0) {
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
          No transcript segments available
        </Typography>
      </Box>
    );
  }

  return (
    <Box 
      className={className}
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        ...style,
      }}
    >
      <Box sx={{ p: 2, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 1 }}>
        <Typography variant="h6">Transcript Segments</Typography>
        <Chip 
          label={`${segmentsWithOrder.length} segments`}
          size="small"
          color="primary"
        />
        <Typography variant="caption" color="text.secondary">
          Drag to reorder
        </Typography>
      </Box>
      
      <Box ref={containerRef} sx={{ flex: 1, overflow: 'auto', px: 2, pb: 2 }}>

      <DragDropContext 
        onDragStart={handleDragStart} 
        onDragEnd={handleDragEnd}
        onBeforeCapture={() => {
          // Ensure the container is ready for drag operations
          if (containerRef.current) {
            containerRef.current.style.position = 'relative';
          }
        }}
      >
        <Droppable 
          droppableId="transcript-segments"
          type="SEGMENT"
          isDropDisabled={false}
          direction="vertical"
          ignoreContainerClipping={true}
        >
          {(provided, snapshot) => (
            <Box
              {...provided.droppableProps}
              ref={provided.innerRef}
              sx={{
                minHeight: '200px',
                backgroundColor: snapshot.isDraggingOver ? 'rgba(144, 202, 249, 0.05)' : 'transparent',
                borderRadius: 2,
                padding: 1,
                border: snapshot.isDraggingOver ? '1px dashed rgba(144, 202, 249, 0.3)' : '1px dashed transparent',
                transition: 'all 0.2s ease',
              }}
            >
              {segmentsWithOrder.map((segment, index) => {
                const isCurrent = segment.id === currentSegmentId;
                
                return (
                  <Draggable
                    key={segment.id}
                    draggableId={segment.id}
                    index={index}
                  >
                    {(provided, snapshot) => (
                      <Paper
                        ref={provided.innerRef}
                        {...provided.draggableProps}
                        style={{
                          ...getSegmentStyle(segment, snapshot.isDragging),
                          // Let the library handle positioning completely
                          ...provided.draggableProps.style,
                        }}
                        onClick={() => handleSegmentClick(segment)}
                      >
                        {/* Drag Handle */}
                        <Box
                          {...provided.dragHandleProps}
                          sx={{
                            position: 'absolute',
                            left: 8,
                            top: '50%',
                            transform: 'translateY(-50%)',
                            cursor: 'grab',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            width: 24,
                            height: 24,
                            borderRadius: '4px',
                            backgroundColor: 'rgba(25, 118, 210, 0.1)',
                            border: '1px solid rgba(25, 118, 210, 0.2)',
                            color: '#1976d2',
                            transition: 'all 0.2s ease',
                            '&:hover': { 
                              backgroundColor: 'rgba(25, 118, 210, 0.2)',
                              border: '1px solid rgba(25, 118, 210, 0.4)',
                              transform: 'translateY(-50%) scale(1.1)',
                            },
                            '&:active': {
                              cursor: 'grabbing',
                              backgroundColor: 'rgba(25, 118, 210, 0.3)',
                            }
                          }}
                        >
                          <DragIcon fontSize="small" />
                        </Box>

                        {/* Segment Content */}
                        <Box sx={{ 
                          ml: 6,
                          // Make content more visible during drag
                          ...(snapshot.isDragging && {
                            color: '#1976d2',
                            fontWeight: 500,
                          })
                        }}>
                          {/* Segment Header */}
                          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                            <Chip 
                              label={`#${segment.orderIndex + 1}`}
                              size="small"
                              color="primary"
                              sx={{ mr: 2, minWidth: '40px', fontSize: '0.7rem' }}
                            />
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
                                label={`${Math.round((segment.confidence || 1) * 100)}%`}
                                size="small"
                                color={(segment.confidence || 1) > 0.8 ? 'success' : 'warning'}
                                sx={{ mr: 1 }}
                              />
                            )}
                            
                            {isCurrent && (
                              <Chip
                                label="Playing"
                                size="small"
                                color="primary"
                                sx={{ mr: 1 }}
                              />
                            )}

                            <Box sx={{ ml: 'auto', display: 'flex', gap: 1 }}>
                              <IconButton
                                size="small"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleSegmentVideo(segment);
                                }}
                                title="Create video clip for this segment"
                              >
                                <ProcessIcon fontSize="small" />
                              </IconButton>
                            </Box>
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

                        </Box>
                      </Paper>
                    )}
                  </Draggable>
                );
              })}
              {provided.placeholder}
            </Box>
          )}
        </Droppable>
      </DragDropContext>
      </Box>
    </Box>
  );
};
