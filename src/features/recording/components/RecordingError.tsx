/**
 * RecordingError Component
 * 
 * Error display with retry option
 */

import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { getRecordingErrorMessage } from '../types';
import type { RecordingError } from '../types';

interface RecordingErrorProps {
  /** Error that occurred */
  error: RecordingError;
  /** Callback to retry */
  onRetry: () => void;
  /** Callback to reset */
  onReset: () => void;
  /** Custom className */
  className?: string;
}

export function RecordingError({
  error,
  onRetry,
  onReset,
  className = '',
}: RecordingErrorProps) {
  const message = getRecordingErrorMessage(error);

  return (
    <div className={`space-y-4 ${className}`}>
      <div className="flex items-start gap-3 p-4 bg-destructive/10 rounded-xl">
        <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <h3 className="font-semibold text-destructive mb-1">Recording Error</h3>
          <p className="text-sm text-muted-foreground">{message}</p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          onClick={onReset}
          className="flex-1"
        >
          Start Over
        </Button>
        <Button
          onClick={onRetry}
          className="flex-1"
        >
          <RefreshCw className="h-4 w-4 mr-2" />
          Try Again
        </Button>
      </div>
    </div>
  );
}


