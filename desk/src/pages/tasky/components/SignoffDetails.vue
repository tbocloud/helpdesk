<template>
  <!-- the full page's project-type sections and their tables (TBO's Sign-off requirements,
       Edit in full page: "all fields, including the project-type sections and their tables") -->
  <div v-if="groups.length" class="flex flex-col gap-6">
    <section
      v-for="group in groups"
      :key="group.key"
      class="flex flex-col gap-3"
      :aria-labelledby="`${id}-${group.key}`"
    >
      <h3 :id="`${id}-${group.key}`" class="text-base-medium text-ink-gray-9">
        {{ group.title }}
      </h3>
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <SignoffDetailField
          v-for="field in group.fields"
          :key="field"
          :f="f"
          :field="field"
        />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed, useId } from "vue";
import type { SignoffForm } from "../useSignoffForm";
import SignoffDetailField from "./SignoffDetailField.vue";

const props = defineProps<{ f: SignoffForm }>();
const id = `signoff-details-${useId()}`;

// the documents' section names
const TITLES: Record<string, string> = {
  environment: "Environment",
  requirement: "Requirement reference",
  modules: "Modules covered",
  uat: "UAT details",
  open_items: "Known exceptions accepted by the customer",
  training: "Training",
  migration: "Data migration",
  go_live: "Go-Live",
  support: "Support",
  engagement: "Engagement",
  period: "Period",
  deliverables: "Deliverables",
  performance: "Performance summary",
  ad_spend: "Ad spend",
  carry_forward: "Carry-forward items",
  next_plan: "Next period plan",
  website: "Website go-live",
  attachments: "Attachments",
};

/** The stage's sections with their fields, each field once (a later section that shares one
 * shows only what is new to it). */
const groups = computed(() => {
  const seen = new Set<string>();
  return props.f.shownSections
    .map((key) => {
      const fields = (props.f.data?.sections[key] ?? []).filter(
        (field) => !seen.has(field) && props.f.data?.fields[field]
      );
      fields.forEach((field) => seen.add(field));
      return { key, title: __(TITLES[key] ?? key), fields };
    })
    .filter((g) => g.fields.length);
});
</script>
