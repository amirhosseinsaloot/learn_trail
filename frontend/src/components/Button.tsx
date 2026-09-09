import { useId, type ButtonHTMLAttributes, type MouseEvent, type ReactNode } from 'react';

import { SpinnerIcon } from './icons';

type ButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'disabled'> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'base' | 'lg';
  block?: boolean;
  /** Disabled buttons stay focusable so the reason can be announced (DESIGN.html section 3). */
  disabled?: boolean;
  disabledReason?: string;
  /** A busy button shows a spinner and keeps its width. */
  busy?: boolean;
  children: ReactNode;
};

export function Button({
  variant = 'secondary',
  size = 'base',
  block = false,
  disabled = false,
  disabledReason,
  busy = false,
  className,
  onClick,
  type = 'button',
  children,
  ...rest
}: ButtonProps) {
  const reasonId = useId();
  const inert = disabled || busy;
  const classes = [
    'btn',
    `btn--${variant}`,
    size === 'base' ? '' : `btn--${size}`,
    block ? 'btn--block' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');

  function handleClick(event: MouseEvent<HTMLButtonElement>) {
    if (inert) {
      event.preventDefault();
      return;
    }
    onClick?.(event);
  }

  const showReason = disabled && disabledReason !== undefined;
  // The reason sits outside the button so it describes it without joining its name.
  return (
    <>
      <button
        {...rest}
        type={type}
        className={classes}
        aria-disabled={inert || undefined}
        aria-busy={busy || undefined}
        aria-describedby={showReason ? reasonId : rest['aria-describedby']}
        onClick={handleClick}
      >
        <span className="btn__label">{children}</span>
        {busy ? <SpinnerIcon className="btn__spinner" /> : null}
      </button>
      {showReason ? (
        <span className="sr-only" id={reasonId}>
          {disabledReason}
        </span>
      ) : null}
    </>
  );
}
