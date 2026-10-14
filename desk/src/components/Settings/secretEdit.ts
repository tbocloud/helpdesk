import type { SecretEdit } from "./SecretField.vue";

/** What a SecretField's edit sends on save: a new value, "" to remove it, or nothing. */
export function secretValue(edit: SecretEdit | undefined): string | undefined {
  if (edit?.mode === "remove") return "";
  if (edit?.mode === "replace" && edit.value.trim()) return edit.value.trim();
  return undefined;
}
