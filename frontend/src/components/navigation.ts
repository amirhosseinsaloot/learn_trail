import type { ComponentType } from 'react';

import { AskIcon, BookIcon, ChatIcon, PersonIcon } from './icons';

export type Section = 'conversations' | 'library' | 'ask' | 'account';

export interface NavigationItem {
  section: Section;
  to: string;
  railLabel: string;
  tabLabel: string;
  icon: ComponentType<{ size?: number }>;
}

/** Sections in reading order (DESIGN.html section 4). */
export const navigationItems: NavigationItem[] = [
  {
    section: 'conversations',
    to: '/',
    railLabel: 'Conversations',
    tabLabel: 'Chats',
    icon: ChatIcon,
  },
  { section: 'library', to: '/library', railLabel: 'Library', tabLabel: 'Library', icon: BookIcon },
  { section: 'ask', to: '/ask', railLabel: 'Ask', tabLabel: 'Ask', icon: AskIcon },
  {
    section: 'account',
    to: '/account',
    railLabel: 'Account',
    tabLabel: 'Account',
    icon: PersonIcon,
  },
];

export function sectionOf(pathname: string): Section | null {
  if (pathname === '/' || pathname.startsWith('/c/')) return 'conversations';
  if (pathname === '/library' || pathname.startsWith('/library/')) return 'library';
  if (pathname === '/ask') return 'ask';
  if (pathname === '/account') return 'account';
  return null;
}
