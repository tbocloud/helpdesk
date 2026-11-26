import { __ } from "@/translation";

/** A person on the sales team, as helpdesk.api.sales_team.get_team gives them. */
export interface TeamMember {
  user: string;
  full_name: string;
  user_image?: string | null;
  roles: string[];
}

export interface TeamCandidate {
  user: string;
  full_name: string;
}

/** What each team role lets the person do, for the roles picker. */
export const ROLE_HINTS: Record<string, string> = {
  "Sales User": __(
    "Works leads and Today's calls, and is given sales targets."
  ),
  "Presales Executive": __("Is given sales targets; no Today's calls."),
  "Sales Employee": __(
    "Sees the sales screens only: no tasks, projects or tickets."
  ),
};
