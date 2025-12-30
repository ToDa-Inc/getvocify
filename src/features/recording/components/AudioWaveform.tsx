/**
 * AudioWaveform Component
 * 
 * Real-time waveform visualization using audio analyser data
 */

import { useMemo } from 'react';
import type { AudioVisualization } from '../types';

interface AudioWaveformProps {
  /** Visualization data from useMediaRecorder */
  visualization: AudioVisualization;
  /** Whether recording is active */
  isRecording: boolean;
  /** Number of bars to display */
  bars?: number;
  /** Custom className */
  className?: string;
}

export function AudioWaveform({
  visualization,
  isRecording,
  bars = 9,
  className = '',
}: AudioWaveformProps) {
  // Use recent levels for display
  const displayLevels = useMemo(() => {
    if (!visualization.levels.length) {
      return Array(bars).fill(0);
    }
    
    // Take the most recent levels, or pad with zeros
    const recent = visualization.levels.slice(-bars);
    return [...recent, ...Array(Math.max(0, bars - recent.length)).fill(0)];
  }, [visualization.levels, bars]);

  return (
    <div className={`flex items-center justify-center gap-1.5 ${className}`}>
      {displayLevels.map((level, i) => {
        // Normalize level to height (min 4px, max 40px)
        const height = Math.max(4, level * 40);
        const opacity = isRecording ? 1 : 0.5;
        
        return (
          <div
            key={i}
            className={`w-1.5 rounded-full transition-all duration-150 ${
              isRecording ? 'bg-destructive' : 'bg-muted-foreground/30'
            }`}
            style={{
              height: `${height}px`,
              opacity,
              animation: isRecording
                ? `soundWave 0.8s ease-in-out ${i * 0.08}s infinite`
                : 'none',
            }}
          />
        );
      })}
    </div>
  );
}


