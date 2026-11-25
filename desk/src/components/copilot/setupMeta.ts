// Adding a customer to Copilot (Phase 30, helpdesk.api.copilot_setup): shared types.

export const SETUP_API = "helpdesk.api.copilot_setup";

export type CheckState = "done" | "missing" | "later";

export type SetupCheck = {
  key: string;
  label: string;
  state: CheckState;
  detail: string;
};

export type SetupConnection = {
  name: string;
  site_url: string;
  status: string;
  checked: string;
  new_client: boolean;
  client_version: string;
};

export type SetupApp = {
  app: string;
  branch: string;
  commit: string;
  drift: string;
};

export type SetupCard = {
  name: string;
  environment: string;
  connection: string;
  site_url: string;
  press_site: string;
  press_release_group: string;
  shared_group: boolean;
  apps: SetupApp[];
  apps_read: string;
};

export type Person = { user: string; name: string };

export type CopilotSetup = {
  customer: string;
  switches: { enabled: boolean; level: string; watch: boolean };
  levels: string[];
  default_level: string;
  copilot: { enabled: boolean; shadow: boolean };
  work_goes_to: {
    developers: Person[];
    developers_from: "owner" | "customer" | "common";
    fix_approvers: Person[];
    coordinators: Person[];
    coordinators_from: "customer" | "common";
  };
  connections: SetupConnection[];
  cards: SetupCard[];
  checks: SetupCheck[];
  ready: { done: number; of: number; needs: string[] };
  can: { switches: boolean; add_card: boolean; edit_card: boolean };
};

export type SetupRow = {
  customer: string;
  sites: string[];
  enabled: boolean;
  level: string;
  cards: number;
  production_card: boolean;
  ready: { done: number; of: number; needs: string[] };
  tickets: number;
};

/** The look of a checklist line: its badge text and colours. */
export const CHECK_LOOK: Record<
  CheckState,
  { label: string; badge: "green" | "red" | "gray" }
> = {
  done: { label: "Done", badge: "green" },
  missing: { label: "Needed", badge: "red" },
  later: { label: "Later", badge: "gray" },
};
