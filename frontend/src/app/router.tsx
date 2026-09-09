import { createBrowserRouter, type RouteObject } from 'react-router';

import { EntryLayout, Layout } from '../components/Layout';
import {
  Account,
  Ask,
  ConversationThread,
  ConversationsHome,
  Library,
  NewConversation,
  NotFound,
  Register,
  SavedSummary,
  SignIn,
  SummaryReview,
} from './screens';

/** Every path from DESIGN.html section 4. Guards for signed-in routes arrive in NU-016. */
export const routes: RouteObject[] = [
  {
    element: <EntryLayout />,
    children: [
      { path: '/login', element: <SignIn /> },
      { path: '/register', element: <Register /> },
    ],
  },
  {
    element: <Layout />,
    children: [
      { path: '/', element: <ConversationsHome />, handle: { list: 'conversations' } },
      { path: '/c/new', element: <NewConversation />, handle: { list: 'conversations' } },
      { path: '/c/:id', element: <ConversationThread />, handle: { list: 'conversations' } },
      { path: '/c/:id/summary', element: <SummaryReview />, handle: { list: 'conversations' } },
      { path: '/library', element: <Library />, handle: { list: 'summaries' } },
      { path: '/library/:id', element: <SavedSummary />, handle: { list: 'summaries' } },
      { path: '/ask', element: <Ask /> },
      { path: '/account', element: <Account /> },
      { path: '*', element: <NotFound /> },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
