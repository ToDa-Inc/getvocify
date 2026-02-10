/**
 * useMediaRecorder Hook
 * 
 * Handles browser audio recording using the MediaRecorder API.
 * Provides recording state, duration tracking, and audio visualization.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { AUDIO } from '@/shared/lib/constants';
import type {
  RecordingState,
  RecordingError,
  RecordedAudio,
  AudioVisualization,
  UseMediaRecorderReturn,
} from '../types';

/**
 * Check if MediaRecorder is supported
 */
function isMediaRecorderSupported(): boolean {
  return typeof MediaRecorder !== 'undefined';
}

/**
 * Get the best supported audio MIME type
 */
function getSupportedMimeType(): string {
  const types = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
  ];

  for (const type of types) {
    if (MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }

  return 'audio/webm'; // Fallback
}

/**
 * Hook for recording audio using MediaRecorder API
 */
export function useMediaRecorder(): UseMediaRecorderReturn {
  // State
  const [state, setState] = useState<RecordingState>('idle');
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState<RecordingError | null>(null);
  const [audio, setAudio] = useState<RecordedAudio | null>(null);
  const [visualization, setVisualization] = useState<AudioVisualization>({
    level: 0,
    levels: [],
    isActive: false,
  });

  // Refs
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  // Cleanup function
  const cleanup = useCallback(() => {
    // Stop timer
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    // Stop animation frame
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    // Stop media recorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    mediaRecorderRef.current = null;

    // Close AudioContext (CRITICAL: prevents memory leak)
    if (audioContextRef.current) {
      audioContextRef.current.close().catch((err) => {
        console.warn('Failed to close AudioContext:', err);
      });
      audioContextRef.current = null;
    }

    // Stop media stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }

    // Clear analyser
    analyserRef.current = null;

    // Clear chunks
    chunksRef.current = [];
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  // Update visualization
  const updateVisualization = useCallback(() => {
    if (!analyserRef.current || state !== 'recording') return;

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);

    // Calculate average level
    const average = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
    const normalizedLevel = Math.min(average / 128, 1);

    setVisualization(prev => ({
      level: normalizedLevel,
      levels: [...prev.levels.slice(-29), normalizedLevel], // Keep last 30 levels
      isActive: normalizedLevel > 0.05,
    }));

    animationFrameRef.current = requestAnimationFrame(updateVisualization);
  }, [state]);

  // Start recording
  const start = useCallback(async (): Promise<MediaStream | null> => {
    // Check support
    if (!isMediaRecorderSupported()) {
      setError('not_supported');
      setState('error');
      return null;
    }

    try {
      setState('requesting');

      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      streamRef.current = stream;

      // Set up audio analyser for visualization
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;  // Store for cleanup
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      // Create MediaRecorder
      const mimeType = getSupportedMimeType();
      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      // Handle data
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      // Handle stop
      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const url = URL.createObjectURL(blob);
        const recordingDuration = (Date.now() - startTimeRef.current) / 1000;

        // Close AudioContext when recording stops (prevents memory leak)
        if (audioContextRef.current) {
          audioContextRef.current.close().catch((err) => {
            console.warn('Failed to close AudioContext on stop:', err);
          });
          audioContextRef.current = null;
        }

        // Validate duration
        if (recordingDuration < AUDIO.MIN_DURATION_SECONDS) {
          setError('duration_too_short');
          setState('error');
          URL.revokeObjectURL(url);
          return;
        }

        // Validate size
        if (blob.size > AUDIO.MAX_FILE_SIZE_BYTES) {
          setError('file_too_large');
          setState('error');
          URL.revokeObjectURL(url);
          return;
        }

        setAudio({
          blob,
          url,
          duration: recordingDuration,
          mimeType,
          size: blob.size,
        });
        setState('stopped');
      };

      // Handle error
      mediaRecorder.onerror = () => {
        setError('recording_failed');
        setState('error');
        cleanup();
      };

      // Start recording
      mediaRecorder.start(1000); // Collect data every second
      startTimeRef.current = Date.now();
      setState('recording');
      setDuration(0);
      setError(null);

      // Start duration timer
      timerRef.current = window.setInterval(() => {
        const elapsed = (Date.now() - startTimeRef.current) / 1000;
        setDuration(elapsed);

        // Auto-stop at max duration
        if (elapsed >= AUDIO.MAX_DURATION_SECONDS) {
          mediaRecorder.stop();
          cleanup();
        }
      }, 100);

      // Start visualization
      updateVisualization();

      return stream;

    } catch (err) {
      console.error('Failed to start recording:', err);

      if (err instanceof DOMException) {
        if (err.name === 'NotAllowedError') {
          setError('permission_denied');
        } else if (err.name === 'NotFoundError') {
          setError('no_audio_device');
        } else {
          setError('recording_failed');
        }
      } else {
        setError('unknown');
      }

      setState('error');
      cleanup();
      return null;
    }
  }, [cleanup, updateVisualization]);

  // Stop recording
  const stop = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    
    // We DON'T call cleanup() here anymore because it stops the stream tracks
    // and closes the AudioContext, which kills the realtime transcription.
    // Instead, we just stop the timer and visualization.
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  }, []);

  // Cancel recording
  const cancel = useCallback(() => {
    cleanup();
    setDuration(0);
    setAudio(null);
    setState('idle');
    setVisualization({ level: 0, levels: [], isActive: false });
  }, [cleanup]);

  // Reset to idle
  const reset = useCallback(() => {
    // Revoke previous audio URL
    if (audio?.url) {
      URL.revokeObjectURL(audio.url);
    }
    
    cleanup();
    setDuration(0);
    setAudio(null);
    setError(null);
    setState('idle');
    setVisualization({ level: 0, levels: [], isActive: false });
  }, [audio?.url, cleanup]);

  return {
    state,
    duration,
    error,
    audio,
    visualization,
    stream: streamRef.current,
    start,
    stop,
    cancel,
    reset,
  };
}


