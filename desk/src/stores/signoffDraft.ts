import type { CarriedSignoff } from "@/pages/tasky/useSignoffForm";
import { defineStore } from "pinia";
import { ref } from "vue";

/**
 * A New sign-off dialog's unsaved form, handed to the full page by Edit in full page: kept in
 * the browser only, so a dialog that is abandoned leaves no draft behind (TBO's Sign-off
 * requirements, Edit in full page). Taken once by the page it was meant for.
 */
export const useSignoffDraftStore = defineStore("signoffDraft", () => {
  const drafts = ref<Record<string, CarriedSignoff>>({});

  function key(projectId: string, uat: boolean) {
    return `${projectId}:${uat ? "uat" : "training"}`;
  }

  function keep(projectId: string, uat: boolean, draft: CarriedSignoff) {
    drafts.value[key(projectId, uat)] = draft;
  }

  function take(projectId: string, uat: boolean): CarriedSignoff | null {
    const k = key(projectId, uat);
    const draft = drafts.value[k] ?? null;
    delete drafts.value[k];
    return draft;
  }

  return { keep, take };
});
