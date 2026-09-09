import type { ReactNode } from 'react';

interface EmptyProps {
  title: string;
  /** One sentence. */
  description: string;
  /** One primary action. */
  action?: ReactNode;
}

export function Empty({ title, description, action }: EmptyProps) {
  return (
    <div className="empty">
      <h2 className="empty__title">{title}</h2>
      <p>{description}</p>
      {action === undefined ? null : <div className="empty__action">{action}</div>}
    </div>
  );
}
