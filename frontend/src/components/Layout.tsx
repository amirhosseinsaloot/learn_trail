import { useEffect, useRef, type RefObject } from 'react';
import { Outlet, useLocation, useMatches } from 'react-router';

import { Rail } from './Rail';
import { SkipLink } from './SkipLink';
import { TabBar } from './TabBar';

export type ListSlot = 'conversations' | 'summaries';

/** Routes declare `handle: { list }` to show the matching context list. */
export function listSlotOf(matches: ReturnType<typeof useMatches>): ListSlot | null {
  for (const match of [...matches].reverse()) {
    const handle = match.handle;
    if (typeof handle === 'object' && handle !== null && 'list' in handle) {
      const list = handle.list;
      if (list === 'conversations' || list === 'summaries') return list;
    }
  }
  return null;
}

/** After a route change, focus moves to the screen's h1 (DESIGN.html section 16). */
function useFocusHeadingOnRouteChange(mainRef: RefObject<HTMLElement | null>) {
  const { pathname } = useLocation();
  const previousPathname = useRef<string | null>(null);
  useEffect(() => {
    if (previousPathname.current !== null && previousPathname.current !== pathname) {
      mainRef.current?.querySelector<HTMLElement>('h1')?.focus();
    }
    previousPathname.current = pathname;
  }, [pathname, mainRef]);
}

const listPlaceholders: Record<ListSlot, { label: string; text: string }> = {
  conversations: { label: 'Conversations', text: 'Your conversations will be listed here.' },
  summaries: { label: 'Saved summaries', text: 'Your saved summaries will be listed here.' },
};

/** Signed-in shell: rail, context list, main column, and the mobile tab bar. */
export function Layout() {
  const mainRef = useRef<HTMLElement>(null);
  useFocusHeadingOnRouteChange(mainRef);
  const list = listSlotOf(useMatches());
  return (
    <>
      <SkipLink />
      <header className="topbar">
        <span className="rail__wordmark">Nuroli</span>
      </header>
      <div className={list === null ? 'shell shell--no-list' : 'shell'}>
        <Rail />
        {list === null ? null : (
          <section className="shell__list" aria-label={listPlaceholders[list].label}>
            <p>{listPlaceholders[list].text}</p>
          </section>
        )}
        <main id="main" className="shell__main" tabIndex={-1} ref={mainRef}>
          <Outlet />
        </main>
      </div>
      <TabBar />
    </>
  );
}

/** Public entry shell for sign-in and registration: no rail, same landmarks. */
export function EntryLayout() {
  const mainRef = useRef<HTMLElement>(null);
  useFocusHeadingOnRouteChange(mainRef);
  return (
    <div className="entry">
      <SkipLink />
      <header className="entry__header">Nuroli</header>
      <main id="main" className="shell__main" tabIndex={-1} ref={mainRef}>
        <Outlet />
      </main>
    </div>
  );
}
