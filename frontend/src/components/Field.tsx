import type { InputHTMLAttributes } from 'react';

type FieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> & {
  id: string;
  label: string;
  hint?: string;
  error?: string;
};

/** Label above, hint below, error below in danger red bound with aria-describedby. */
export function Field({ id, label, hint, error, className, ...inputProps }: FieldProps) {
  const hintId = hint === undefined ? undefined : `${id}-hint`;
  const errorId = error === undefined ? undefined : `${id}-error`;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;
  const classes = ['input', error === undefined ? '' : 'input--invalid', className ?? '']
    .filter(Boolean)
    .join(' ');
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <input
        {...inputProps}
        id={id}
        className={classes}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={describedBy}
      />
      {hint === undefined ? null : (
        <p className="field__hint" id={hintId}>
          {hint}
        </p>
      )}
      {error === undefined ? null : (
        <p className="field__error" id={errorId}>
          {error}
        </p>
      )}
    </div>
  );
}
