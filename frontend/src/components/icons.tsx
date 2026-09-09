// Inline SVG icons (DESIGN.html section 3): 16px in controls, 20px in
// navigation, stroke 1.75, always aria-hidden next to a visible or
// screen-reader label.
import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({ size = 16, children, ...rest }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...rest}
    >
      {children}
    </svg>
  );
}

export function ChatIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v9a1.5 1.5 0 0 1-1.5 1.5H9l-4.5 4v-4A1.5 1.5 0 0 1 4 14.5z" />
    </Icon>
  );
}

export function BookIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5z" />
      <path d="M13 4h5.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H13z" />
    </Icon>
  );
}

export function AskIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M9.5 9.5a2.5 2.5 0 1 1 3.6 2.2c-.7.4-1.1.9-1.1 1.6" />
      <path d="M12 16.5h.01" />
    </Icon>
  );
}

export function PersonIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5 19.5c1.2-3.3 3.6-5 7-5s5.8 1.7 7 5" />
    </Icon>
  );
}

export function DotIcon(props: IconProps) {
  return (
    <Icon size={10} {...props}>
      <circle cx="12" cy="12" r="5" fill="currentColor" stroke="none" />
    </Icon>
  );
}

export function SpinnerIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 3.5a8.5 8.5 0 1 0 8.5 8.5" />
    </Icon>
  );
}
