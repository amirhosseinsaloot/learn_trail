import { Link, useLocation } from 'react-router';

import { navigationItems, sectionOf } from './navigation';

/** Mobile bottom navigation, shown at 820px and below. */
export function TabBar() {
  const active = sectionOf(useLocation().pathname);
  return (
    <nav aria-label="Main" className="tabbar">
      <ul className="tabbar__list">
        {navigationItems.map(({ section, to, tabLabel, icon: Icon }) => (
          <li key={section}>
            <Link
              to={to}
              className="tabbar__link"
              aria-current={active === section ? 'page' : undefined}
            >
              <Icon size={20} />
              <span>{tabLabel}</span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
