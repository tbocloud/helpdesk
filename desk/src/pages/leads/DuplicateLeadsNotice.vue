<template>
  <div
    v-if="matches.length"
    role="status"
    class="flex flex-col gap-2 rounded-md bg-warning-soft px-3 py-2 text-p-sm text-ink-gray-8"
  >
    <p class="flex items-start gap-2 font-medium text-warning">
      <LucideTriangleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      {{ title }}
    </p>
    <ul role="list" class="flex flex-col gap-1.5">
      <li
        v-for="match in matches"
        :key="match.name"
        class="flex flex-wrap items-center gap-x-2 gap-y-0.5"
      >
        <router-link
          :to="{ name: 'Lead', params: { leadId: match.name } }"
          target="_blank"
          class="inline-flex items-center gap-1 font-medium text-ink-gray-9 underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ match.lead_name || match.name }}
          <LucideExternalLink class="size-3.5" aria-hidden="true" />
          <span class="sr-only">{{ __("(opens in a new tab)") }}</span>
        </router-link>
        <span class="min-w-0 text-p-xs text-ink-gray-7">
          {{
            [
              match.company_name,
              match.owner_name || ownerName(options, match.lead_owner),
              stageLabel(options, match.tbo_stage),
              __("Same {0}", matchedOn(match)),
            ]
              .filter(Boolean)
              .join(" · ")
          }}
        </span>
        <Button
          v-if="canMerge"
          class="ml-auto"
          size="sm"
          :label="__('Merge')"
          :aria-label="
            __('Merge {0} with this lead', match.lead_name || match.name)
          "
          @click="emit('merge', match)"
        >
          <template #prefix>
            <LucideMerge class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button } from "frappe-ui";
import { computed } from "vue";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideMerge from "~icons/lucide/merge";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import {
  leadOptions,
  ownerName,
  stageLabel,
  type DuplicateLead,
  type LeadOptions,
} from "./leads";

/** Other leads that share an email, phone or company with what is being typed. */
defineProps<{
  matches: DuplicateLead[];
  title: string;
  /** a manager or head: each match gets a Merge button */
  canMerge?: boolean;
}>();
const emit = defineEmits<{ (e: "merge", match: DuplicateLead): void }>();

const options = computed(() => leadOptions.data as LeadOptions | undefined);

function matchedOn(match: DuplicateLead) {
  const names = {
    email: __("email"),
    phone: __("phone"),
    company: __("company"),
  };
  return match.matched_on.map((m) => names[m]).join(" + ");
}
</script>
