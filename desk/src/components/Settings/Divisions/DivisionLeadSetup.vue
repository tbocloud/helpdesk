<template>
  <SettingsLayoutBase
    :title="__('Lead setup')"
    :description="
      __(
        'The lead departments and Lead Bank referral of {0}, on its own ERP site. A country with no department sends its Lead Bank leads to a waiting list.',
        [divisionName]
      )
    "
  >
    <template #content>
      <div class="flex flex-col gap-8">
        <LeadDepartments :people="people" />
        <ReferralSettings />
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { DIVISIONS_API } from "@/pages/divisions/divisions";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { createResource } from "frappe-ui";
import { computed } from "vue";
import LeadDepartments from "../CRM/LeadDepartments.vue";
import ReferralSettings from "../CRM/ReferralSettings.vue";
import type { DivisionAgent } from "./divisionAgents";

// the hub calls the ERP site of the active division as the admin, who is a Sales Manager there
// (divisions.ERP_SALES_ROLES); that site decides what they may change
const auth = useAuthStore();
const division = computed(() =>
  auth.divisions.find((d) => d.name === auth.activeDivision)
);
const divisionName = computed(
  () => division.value?.division_name || auth.activeDivision || ""
);

const agents = createResource({
  url: `${DIVISIONS_API}.get_division_agents`,
  params: { division: auth.activeDivision },
  auto: !!auth.activeDivision,
});
const people = computed(() =>
  ((agents.data?.agents ?? []) as DivisionAgent[]).map((a) => ({
    user: a.user,
    full_name: a.full_name,
  }))
);
</script>
