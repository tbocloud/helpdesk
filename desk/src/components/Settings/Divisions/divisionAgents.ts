import { DIVISIONS_API } from "@/pages/divisions/divisions";
import { useAuthStore } from "@/stores/auth";
import { createResource } from "frappe-ui";
import { computed, ref, watch } from "vue";

// the roles that run a division; the server checks them again (divisions.MANAGE_ROLES)
const RUNS_DIVISION = ["Group Admin", "Division Admin"];

export interface DivisionAgent {
  user: string;
  full_name: string;
  user_image: string | null;
  is_active: boolean;
  role: string;
}

export interface DivisionInvite {
  name: string;
  email: string;
  division_role: string;
}

// the division both screens show, kept while Settings stays open
const picked = ref("");

/** The divisions a division admin runs, the one picked, and its agents and invites. */
export function useDivisionAgents() {
  const auth = useAuthStore();
  const divisions = computed(() =>
    auth.divisions.filter((d) => RUNS_DIVISION.includes(d.role ?? ""))
  );
  if (!divisions.value.some((d) => d.name === picked.value)) {
    picked.value =
      divisions.value.find((d) => d.name === auth.activeDivision)?.name ||
      divisions.value[0]?.name ||
      "";
  }
  const agents = createResource({
    url: `${DIVISIONS_API}.get_division_agents`,
    makeParams: () => ({ division: picked.value }),
  });
  watch(picked, (division) => division && agents.reload(), { immediate: true });
  return { divisions, picked, agents };
}
