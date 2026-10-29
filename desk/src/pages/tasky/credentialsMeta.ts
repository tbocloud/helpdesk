/** One login in a handover; the password is never part of it (`has_password` only). */
export interface Credential {
  name: string;
  platform: string;
  account_url?: string | null;
  username?: string | null;
  two_factor_contact?: string | null;
  notes?: string | null;
  has_password: boolean;
  /** a hand-back row points at the received login it returns */
  returned_from?: string | null;
}

export interface CredentialHandover {
  name: string;
  direction: "Received from client" | "Returned to client";
  handed_over_on: string;
  handed_over_by?: string | null;
  received_by_name?: string | null;
  client_signoff_name?: string | null;
  signed_on?: string | null;
  close_reason?: string | null;
  remarks?: string | null;
  items: Credential[];
}

export interface CredentialsData {
  project_status: string;
  platforms: string[];
  handovers: CredentialHandover[];
}

export const RETURNED = "Returned to client";
/** How long a shown password stays on screen. */
export const REVEAL_SECONDS = 30;
