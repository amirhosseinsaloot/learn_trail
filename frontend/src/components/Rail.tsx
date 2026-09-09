import { Link, useLocation } from 'react-router';

import { navigationItems, sectionOf } from './navigation';

/** Desktop navigation: 216px with labels, icons only under 1100px. */
export function Rail() {
  const active = sectionOf(useLocation().pathname);
  return (
    <div className="rail">
      <header className="rail__brand">
        <span className="rail__wordmark">Nuroli</span>
        <span className="rail__user">Not signed in</span>
      </header>
      <nav aria-label="Main" className="rail__nav">
        <ul className="rail__list">
          {navigationItems.map(({ section, to, railLabel, icon: Icon }) => (
            <li key={section}>
              <Link
                to={to}
                className="rail__link"
                title={railLabel}
                aria-current={active === section ? 'page' : undefined}
              >
                <Icon size={20} />
                <span className="rail__label">{railLabel}</span>
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
