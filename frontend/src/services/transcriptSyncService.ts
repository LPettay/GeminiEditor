/**
 * Transcript Synchronization Service - Handles real-time transcript highlighting.
 * This service can be easily swapped out with different synchronization strategies.
 */

export interface TranscriptWord {
  word: string;
  start: number;
  end: number;
  confidence: number;
}

export interface TranscriptSegment {
  id: string;
  start: number;
  end: number;
  text: string;
  words: TranscriptWord[];
  confidence: number;
  speaker?: string;
}

export interface SyncState {
  currentSegmentId: string | null;
  currentWordIndex: number;
  isPlaying: boolean;
  currentTime: number;
}

export type SyncCallback = (state: SyncState) => void;

export class TranscriptSyncService {
  private segments: TranscriptSegment[] = [];
  private callbacks: Set<SyncCallback> = new Set();
  private currentState: SyncState = {
    currentSegmentId: null,
    currentWordIndex: -1,
    isPlaying: false,
    currentTime: 0,
  };
  private animationFrameId: number | null = null;

  constructor() {
    this.updateLoop = this.updateLoop.bind(this);
  }

  /**
   * Set the transcript segments to synchronize with.
   */
  setSegments(segments: TranscriptSegment[]): void {
    this.segments = segments;
    this.resetSync();
  }

  /**
   * Start synchronization with a video element.
   */
  startSync(videoElement: HTMLVideoElement): void {
    this.videoElement = videoElement;
    this.videoElement.addEventListener('timeupdate', this.handleTimeUpdate);
    this.videoElement.addEventListener('play', this.handlePlay);
    this.videoElement.addEventListener('pause', this.handlePause);
    this.videoElement.addEventListener('seeked', this.handleSeeked);
    
    this.startUpdateLoop();
  }

  /**
   * Stop synchronization and cleanup.
   */
  stopSync(): void {
    if (this.videoElement) {
      this.videoElement.removeEventListener('timeupdate', this.handleTimeUpdate);
      this.videoElement.removeEventListener('play', this.handlePlay);
      this.videoElement.removeEventListener('pause', this.handlePause);
      this.videoElement.removeEventListener('seeked', this.handleSeeked);
      this.videoElement = null;
    }
    
    this.stopUpdateLoop();
  }

  /**
   * Add a callback to be notified of sync state changes.
   */
  addCallback(callback: SyncCallback): void {
    this.callbacks.add(callback);
  }

  /**
   * Remove a callback.
   */
  removeCallback(callback: SyncCallback): void {
    this.callbacks.delete(callback);
  }

  /**
   * Get current sync state.
   */
  getCurrentState(): SyncState {
    return { ...this.currentState };
  }

  /**
   * Find the current segment and word based on time.
   */
  private findCurrentSegmentAndWord(currentTime: number): {
    segmentId: string | null;
    wordIndex: number;
  } {
    for (const segment of this.segments) {
      if (currentTime >= segment.start && currentTime <= segment.end) {
        // Find the current word within the segment
        let wordIndex = -1;
        for (let i = 0; i < segment.words.length; i++) {
          const word = segment.words[i];
          if (currentTime >= word.start && currentTime <= word.end) {
            wordIndex = i;
            break;
          }
        }
        
        // If no specific word is active, find the closest one
        if (wordIndex === -1 && segment.words.length > 0) {
          const timeDiff = segment.words.map((word, index) => ({
            index,
            diff: Math.min(
              Math.abs(currentTime - word.start),
              Math.abs(currentTime - word.end)
            )
          }));
          
          wordIndex = timeDiff.reduce((closest, current) => 
            current.diff < closest.diff ? current : closest
          ).index;
        }
        
        return { segmentId: segment.id, wordIndex };
      }
    }
    
    return { segmentId: null, wordIndex: -1 };
  }

  /**
   * Update sync state based on current time.
   */
  private updateSyncState(): void {
    if (!this.videoElement) return;
    
    const currentTime = this.videoElement.currentTime;
    const isPlaying = !this.videoElement.paused;
    
    const { segmentId, wordIndex } = this.findCurrentSegmentAndWord(currentTime);
    
    // Update state if changed
    const stateChanged = 
      this.currentState.currentSegmentId !== segmentId ||
      this.currentState.currentWordIndex !== wordIndex ||
      this.currentState.isPlaying !== isPlaying ||
      Math.abs(this.currentState.currentTime - currentTime) > 0.1;
    
    if (stateChanged) {
      this.currentState = {
        currentSegmentId: segmentId,
        currentWordIndex: wordIndex,
        isPlaying,
        currentTime,
      };
      
      this.notifyCallbacks();
    }
  }

  /**
   * Notify all callbacks of state changes.
   */
  private notifyCallbacks(): void {
    this.callbacks.forEach(callback => {
      try {
        callback(this.currentState);
      } catch (error) {
        console.error('Error in transcript sync callback:', error);
      }
    });
  }

  /**
   * Reset sync state.
   */
  private resetSync(): void {
    this.currentState = {
      currentSegmentId: null,
      currentWordIndex: -1,
      isPlaying: false,
      currentTime: 0,
    };
    this.notifyCallbacks();
  }

  /**
   * Start the update loop.
   */
  private startUpdateLoop(): void {
    if (this.animationFrameId === null) {
      this.updateLoop();
    }
  }

  /**
   * Stop the update loop.
   */
  private stopUpdateLoop(): void {
    if (this.animationFrameId !== null) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
  }

  /**
   * Update loop using requestAnimationFrame for smooth updates.
   */
  private updateLoop(): void {
    this.updateSyncState();
    this.animationFrameId = requestAnimationFrame(this.updateLoop);
  }

  /**
   * Handle video time updates.
   */
  private handleTimeUpdate = (): void => {
    // This is handled by the update loop for better performance
  };

  /**
   * Handle video play event.
   */
  private handlePlay = (): void => {
    this.updateSyncState();
  };

  /**
   * Handle video pause event.
   */
  private handlePause = (): void => {
    this.updateSyncState();
  };

  /**
   * Handle video seek event.
   */
  private handleSeeked = (): void => {
    this.updateSyncState();
  };

  private videoElement: HTMLVideoElement | null = null;
}

// Singleton instance for global use
export const transcriptSyncService = new TranscriptSyncService();
