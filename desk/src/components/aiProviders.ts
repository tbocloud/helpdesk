/** The two provider sections of Settings → AI providers (helpdesk.ai_engine.SLOTS). */
export type ProviderSlot = "OpenAI" | "Anthropic-compatible";

export interface ProviderState {
  /** has a key and a model */
  configured: boolean;
  model: string | null;
  /** skipped for 30 minutes after a billing, key or model failure */
  paused: boolean;
  /** set while the provider is failing, cleared by its next answer */
  down: { kind: string; reason: string; since: string; model: string } | null;
}

/** helpdesk.ai_engine.provider_status */
export interface ProviderStatus {
  primary: ProviderSlot;
  failover: boolean;
  order: ProviderSlot[];
  /** the provider that answers now, or null when none can */
  in_use: ProviderSlot | null;
  providers: Record<ProviderSlot, ProviderState>;
}

export function providerLabel(status: ProviderStatus, slot: ProviderSlot) {
  const model = status.providers[slot]?.model;
  return model ? `${slot} (${model})` : slot;
}
