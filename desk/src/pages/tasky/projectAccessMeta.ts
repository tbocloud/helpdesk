/** One thing a project runs on (docs/project-access.md); the password is never part of it. */
export interface AccessEntry {
  name: string;
  kind: string;
  environment?: string | null;
  label: string;
  url?: string | null;
  username?: string | null;
  notes?: string | null;
  has_password: boolean;
  added_by?: string | null;
  added_by_name?: string | null;
  modified: string;
}

export interface ProjectAccessData {
  entries: AccessEntry[];
  kinds: string[];
  environments: string[];
  /** adds, changes and shows passwords: the project's managers and developers */
  can_handle: boolean;
}

/** How long a shown password stays on screen. */
export const REVEAL_SECONDS = 30;

/** Anything typed without a scheme opens as https; other schemes never become links. */
export function safeUrl(url: string) {
  const full = /^[a-z][a-z0-9+.-]*:/i.test(url) ? url : `https://${url}`;
  return /^https?:\/\//i.test(full) ? full : null;
}
