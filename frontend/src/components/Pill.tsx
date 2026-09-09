import type { ReactNode } from 'react';

import { DotIcon } from './icons';

interface PillProps {
  tone: 'draft' | 'saved' | 'web' | 'muted' | 'danger';
  /** Always a glyph plus a word; the default glyph is a dot. */
  icon?: ReactNode;
  children: ReactNode;
}

export function Pill({ tone, icon, children }: PillProps) {
  return (
    <span className={`pill pill--${tone}`}>
      {icon ?? <DotIcon />}
      <span>{children}</span>
    </span>
  );
}
