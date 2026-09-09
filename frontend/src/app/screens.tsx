// Placeholder screens for every route in DESIGN.html section 4. Feature
// tickets replace each body; the h1 rule (one per screen, focus target after
// navigation) stays.
import type { ReactNode } from 'react';
import { Link } from 'react-router';

interface ScreenProps {
  title: string;
  children?: ReactNode;
}

export function Screen({ title, children }: ScreenProps) {
  return (
    <div className="screen">
      <h1 className="screen__title" tabIndex={-1}>
        {title}
      </h1>
      {children}
    </div>
  );
}

export function SignIn() {
  return (
    <Screen title="Sign in">
      <p>The sign-in form arrives in NU-016.</p>
    </Screen>
  );
}

export function Register() {
  return (
    <Screen title="Create your account">
      <p>The registration form arrives in NU-016.</p>
    </Screen>
  );
}

export function ConversationsHome() {
  return (
    <Screen title="Conversations">
      <p>Your most recent conversation opens here once conversations exist (NU-028).</p>
    </Screen>
  );
}

export function NewConversation() {
  return (
    <Screen title="New conversation">
      <p>The composer arrives in NU-028; a conversation is created on first send.</p>
    </Screen>
  );
}

export function ConversationThread() {
  return (
    <Screen title="Conversation">
      <p>The thread, streaming replies, stop, and retry arrive in NU-028.</p>
    </Screen>
  );
}

export function SummaryReview() {
  return (
    <Screen title="Review before saving">
      <p>Summary generation, editing, and confirmation arrive in NU-035.</p>
    </Screen>
  );
}

export function Library() {
  return (
    <Screen title="Library">
      <p>Saved knowledge, search, and the archive filter arrive in NU-036.</p>
    </Screen>
  );
}

export function SavedSummary() {
  return (
    <Screen title="Saved summary">
      <p>Summary detail and versions arrive in NU-036.</p>
    </Screen>
  );
}

export function Ask() {
  return (
    <Screen title="Ask my knowledge">
      <p>Questions answered from your confirmed summaries arrive in NU-038.</p>
    </Screen>
  );
}

export function Account() {
  return (
    <Screen title="Account">
      <p>Display name, password change, and sign out arrive in NU-019.</p>
    </Screen>
  );
}

export function NotFound() {
  return (
    <Screen title="Not found">
      <p>There is nothing at this address.</p>
      <Link to="/">Go to your conversations</Link>
    </Screen>
  );
}
