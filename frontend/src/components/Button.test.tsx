import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Button } from './Button';

describe('Button', () => {
  it('stays focusable while disabled and announces the reason', async () => {
    const onClick = vi.fn();
    render(
      <Button disabled disabledReason="Sign in to send messages" onClick={onClick}>
        Send
      </Button>,
    );
    const button = screen.getByRole('button', { name: 'Send' });
    expect(button).not.toBeDisabled();
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button).toHaveAccessibleDescription('Sign in to send messages');
    button.focus();
    expect(button).toHaveFocus();
    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('calls onClick when enabled', async () => {
    const onClick = vi.fn();
    render(
      <Button variant="primary" onClick={onClick}>
        Save
      </Button>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('keeps its label in the tree while busy', () => {
    render(<Button busy>Generating</Button>);
    const button = screen.getByRole('button', { name: 'Generating' });
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(button).toHaveAttribute('aria-disabled', 'true');
  });

  it('defaults to type button so it does not submit forms by accident', () => {
    render(<Button>Cancel</Button>);
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveAttribute('type', 'button');
  });
});
