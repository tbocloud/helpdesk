import { createResource } from "frappe-ui";

/** helpdesk.tasky.api.get_users: an active agent with an enabled account */
export interface AssignablePerson {
  name: string;
  full_name?: string;
}

// one request per page load, shared by the ticket owner pickers and labels
const people = createResource({
  url: "helpdesk.tasky.api.get_users",
  // a failed load shows user IDs and offers Retry in the picker
  onError() {},
});

/**
 * The people who can own tickets or take work, with their names. A person who
 * isn't in the list any more (deactivated) shows as their user ID.
 */
export function useAssignablePeople() {
  if (!people.data && !people.loading) people.fetch();

  function find(user: string | null | undefined) {
    return ((people.data ?? []) as AssignablePerson[]).find(
      (p) => p.name === user
    );
  }

  function nameOf(user: string | null | undefined): string {
    if (!user) return "";
    return find(user)?.full_name || user;
  }

  /** Known to be deactivated: the list loaded and they aren't in it. */
  function isInactive(user: string | null | undefined): boolean {
    return !!user && !!people.data && !find(user);
  }

  return { people, nameOf, isInactive };
}
