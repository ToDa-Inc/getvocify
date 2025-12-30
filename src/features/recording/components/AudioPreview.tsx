/**
 * AudioPreview Component
 * 
 * Playback controls for recorded audio before upload
 */

import { useState, useRef, useEffect } from 'react';
import { Play, Pause, RotateCcw } from 'lucide-react';
import { Button } from '@/ui/button';
import type { RecordedAudio } from '../types';
import { formatFileSize } from '../types';

interface AudioPreviewProps {
  /** Recorded audio data */
  audio: RecordedAudio;
  /** Callback when user wants to re-record */
  onReRecord: () => void;
  /** Callback when user confirms upload */
  onUpload: () => void;
  /** Custom className */
  className?: string;
}

export function AudioPreview({
  audio,
  onReRecord,
  onUpload,
  className = '',
}: AudioPreviewProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    // Create audio element
    const audioEl = new Audio(audio.url);
    audioRef.current = audioEl;

    const updateTime = () => setCurrentTime(audioEl.currentTime);
    audioEl.addEventListener('timeupdate', updateTime);
    audioEl.addEventListener('ended', () => setIsPlaying(false));

    return () => {
      audioEl.removeEventListener('timeupdate', updateTime);
      audioEl.pause();
      audioEl.src = '';
    };
  }, [audio.url]);

  const togglePlayback = () => {
    if (!audioRef.current) return;

    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  const formatDuration = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const progress = audio.duration > 0 ? (currentTime / audio.duration) * 100 : 0;

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Audio Player */}
      <div className="bg-card rounded-2xl shadow-soft p-4">
        <div className="flex items-center gap-4">
          <Button
            variant="outline"
            size="icon"
            onClick={togglePlayback}
            className="rounded-full flex-shrink-0"
          >
            {isPlaying ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4 ml-0.5" />
            )}
          </Button>

          <div className="flex-1">
            <div className="h-2 bg-secondary rounded-full overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-100"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="flex items-center justify-between mt-1 text-xs text-muted-foreground">
              <span>{formatDuration(currentTime)}</span>
              <span>{formatDuration(audio.duration)}</span>
            </div>
          </div>
        </div>

        <div className="mt-3 text-xs text-muted-foreground text-center">
          {formatFileSize(audio.size)} • {audio.mimeType}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          onClick={onReRecord}
          className="flex-1"
        >
          <RotateCcw className="h-4 w-4 mr-2" />
          Re-record
        </Button>
        <Button
          onClick={onUpload}
          className="flex-1"
        >
          Upload & Process
        </Button>
      </div>
    </div>
  );
}


