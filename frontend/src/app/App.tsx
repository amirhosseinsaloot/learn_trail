import '../styles/tokens.css';
import '../styles/base.css';
import '../styles/components.css';
import '../styles/shell.css';

import { RouterProvider } from 'react-router';

import { Providers } from './providers';
import { createAppRouter } from './router';

const router = createAppRouter();

export function App() {
  return (
    <Providers>
      <RouterProvider router={router} />
    </Providers>
  );
}
