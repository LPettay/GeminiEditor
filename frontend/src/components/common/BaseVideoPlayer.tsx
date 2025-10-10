/**
 * Base Video Player - Modular video player that can be easily swapped out.
 * This provides a common interface that different video player implementations can use.
 */

import React, { forwardRef, useImperativeHandle, useRef } from 'react';

export interface VideoPlayerRef {
  play: () => Promise<void>;
  pause: () => void;
  seek: (time: number) => void;
  setVolume: (volume: number) => void;
  getCurrentTime: () => number;
  getDuration: () => number;
  getVideoElement: () => HTMLVideoElement | null;
}

export interface BaseVideoPlayerProps {
  src: string;
  onPlay?: () => void;
  onPause?: () => void;
  onTimeUpdate?: (currentTime: number) => void;
  onLoadedMetadata?: (duration: number) => void;
  onError?: (error: string) => void;
  onLoadStart?: () => void;
  onCanPlay?: () => void;
  onLoadedData?: () => void;
  onWaiting?: () => void;
  onStalled?: () => void;
  className?: string;
  style?: React.CSSProperties;
  controls?: boolean;
  preload?: 'none' | 'metadata' | 'auto';
  crossOrigin?: string;
  playsInline?: boolean;
}

/**
 * Base video player component that provides a common interface.
 * This can be easily swapped out with different video player implementations.
 */
export const BaseVideoPlayer = forwardRef<VideoPlayerRef, BaseVideoPlayerProps>(
  ({
    src,
    onPlay,
    onPause,
    onTimeUpdate,
    onLoadedMetadata,
    onError,
    onLoadStart,
    onCanPlay,
    onLoadedData,
    onWaiting,
    onStalled,
    className,
    style,
    controls = false,
    preload = 'metadata',
    crossOrigin = 'anonymous',
    playsInline = true,
  }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null);

    useImperativeHandle(ref, () => ({
      play: async () => {
        if (videoRef.current) {
          await videoRef.current.play();
        }
      },
      pause: () => {
        if (videoRef.current) {
          videoRef.current.pause();
        }
      },
      seek: (time: number) => {
        if (videoRef.current) {
          videoRef.current.currentTime = time;
        }
      },
      setVolume: (volume: number) => {
        if (videoRef.current) {
          videoRef.current.volume = volume;
        }
      },
      getCurrentTime: () => {
        return videoRef.current?.currentTime || 0;
      },
      getDuration: () => {
        return videoRef.current?.duration || 0;
      },
      getVideoElement: () => {
        return videoRef.current;
      },
    }));

    const handleError = (event: React.SyntheticEvent<HTMLVideoElement, Event>) => {
      const video = event.currentTarget;
      const errorCode = video.error?.code;
      const errorMessage = video.error?.message || 'Unknown error';
      
      let errorText = 'Failed to load video';
      switch (errorCode) {
        case 1:
          errorText = 'Video loading was aborted';
          break;
        case 2:
          errorText = 'Network error occurred while loading video';
          break;
        case 3:
          errorText = 'Video format not supported or corrupted';
          break;
        case 4:
          errorText = 'Video codec not supported by browser';
          break;
      }
      
      onError?.(`${errorText}: ${errorMessage}`);
    };

    return (
      <video
        ref={videoRef}
        src={src}
        className={className}
        style={style}
        controls={controls}
        preload={preload}
        crossOrigin={crossOrigin}
        playsInline={playsInline}
        onPlay={onPlay}
        onPause={onPause}
        onTimeUpdate={(e) => onTimeUpdate?.(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => onLoadedMetadata?.(e.currentTarget.duration)}
        onError={handleError}
        onLoadStart={onLoadStart}
        onCanPlay={onCanPlay}
        onLoadedData={onLoadedData}
        onWaiting={onWaiting}
        onStalled={onStalled}
      />
    );
  }
);

BaseVideoPlayer.displayName = 'BaseVideoPlayer';
