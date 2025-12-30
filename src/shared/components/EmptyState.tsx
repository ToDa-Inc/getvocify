/**
 * EmptyState Component
 * 
 * Displays when a list or collection is empty.
 * Encourages user to take action.
 */

import type { ReactNode } from 'react';
import { Inbox } from 'lucide-react';

interface EmptyStateProps {
  /** Message to display */
  message?: string;
  /** Optional title */
  title?: string;
  /** Optional icon component */
  icon?: ReactNode;
  /** Optional action button/element */
  action?: ReactNode;
  /** Custom className */
  className?: string;
}

export function EmptyState({
  message = 'No items found',
  title,
  icon,
  action,
  className = '',
}: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center p-8 text-center ${className}`}>
      <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
        {icon ?? <Inbox className="h-6 w-6 text-muted-foreground" />}
      </div>
      {title && (
        <h3 className="text-lg font-semibold text-foreground mb-1">{title}</h3>
      )}
      <p className="text-sm text-muted-foreground mb-4 max-w-sm">{message}</p>
      {action && <div>{action}</div>}
    </div>
  );
}


