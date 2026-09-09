import type { ReactNode } from 'react';

interface AlertProps {
  tone: 'error' | 'info' | 'success';
  children: ReactNode;
}

/** Inline near the action that produced it; errors are alerts, the rest status. */
export function Alert({ tone, children }: AlertProps) {
  return (
    <div className={`alert alert--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  );
}
