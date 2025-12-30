/**
 * UploadProgress Component
 * 
 * Progress bar and status during audio upload
 */

import { CheckCircle2 } from 'lucide-react';
import type { UploadProgress as UploadProgressType } from '../types';

interface UploadProgressProps {
  /** Upload progress data */
  progress: UploadProgressType;
  /** Custom className */
  className?: string;
}

export function UploadProgress({
  progress,
  className = '',
}: UploadProgressProps) {
  if (progress.complete) {
    return (
      <div className={`flex items-center justify-center gap-2 text-success ${className}`}>
        <CheckCircle2 className="h-5 w-5" />
        <span className="text-sm font-medium">Upload complete!</span>
      </div>
    );
  }

  return (
    <div className={`space-y-2 ${className}`}>
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">Uploading...</span>
        <span className="font-medium text-foreground">{progress.percent}%</span>
      </div>
      <div className="h-2 bg-secondary rounded-full overflow-hidden">
        <div
          className="h-full bg-primary transition-all duration-300"
          style={{ width: `${progress.percent}%` }}
        />
      </div>
      <div className="text-xs text-muted-foreground text-center">
        {Math.round(progress.loaded / 1024)} KB / {Math.round(progress.total / 1024)} KB
      </div>
    </div>
  );
}


