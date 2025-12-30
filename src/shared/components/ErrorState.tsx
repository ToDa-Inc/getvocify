/**
 * ErrorState Component
 * 
 * Displays an error message with optional retry action.
 * Used when data fetching or operations fail.
 */

import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/ui/button';

interface ErrorStateProps {
  /** Error message to display */
  message?: string;
  /** Optional title */
  title?: string;
  /** Retry callback */
  onRetry?: () => void;
  /** Custom className */
  className?: string;
}

export function ErrorState({
  message = 'Something went wrong',
  title = 'Error',
  onRetry,
  className = '',
}: ErrorStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center p-8 text-center ${className}`}>
      <div className="w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
        <AlertCircle className="h-6 w-6 text-destructive" />
      </div>
      <h3 className="text-lg font-semibold text-foreground mb-1">{title}</h3>
      <p className="text-sm text-muted-foreground mb-4 max-w-sm">{message}</p>
      {onRetry && (
        <Button variant="outline" onClick={onRetry}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Try Again
        </Button>
      )}
    </div>
  );
}


