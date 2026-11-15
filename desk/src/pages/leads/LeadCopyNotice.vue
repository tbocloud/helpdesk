<template>
  <!-- the ERP site can't be reached: what is on screen is the hub's saved copy, read only
       (docs/lead-mirror.md, phase 2a) -->
  <div
    role="status"
    class="flex flex-col gap-3 rounded-xl border border-warning-border bg-warning-panel px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
  >
    <p class="flex min-w-0 items-start gap-2 text-p-sm text-ink-gray-8">
      <LucideCloudOff
        class="mt-0.5 size-4 shrink-0 text-warning"
        aria-hidden="true"
      />
      <span>
        <strong class="font-semibold text-ink-gray-9">{{
          __("The CRM can't be reached right now.")
        }}</strong>
        {{ message }}
      </span>
    </p>
    <Button
      class="shrink-0 self-start sm:self-auto"
      :label="__('Try again')"
      :loading="loading"
      @click="emit('retry')"
    />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, dayjs } from "frappe-ui";
import { computed } from "vue";
import LucideCloudOff from "~icons/lucide/cloud-off";

const props = defineProps<{
  /** when the copy was last brought up to date (the server's time) */
  copiedAt?: string;
  /** the Leads list, where other tabs and filters need the CRM itself */
  list?: boolean;
  loading?: boolean;
}>();
const emit = defineEmits<{ (e: "retry"): void }>();

const message = computed(() => {
  const when = props.copiedAt ? dayjs(props.copiedAt) : null;
  const saved = when?.isValid()
    ? __("You're seeing the copy saved on {0}.", when.format("D MMM, h:mm A"))
    : __("You're seeing a saved copy.");
  const rest = props.list
    ? __(
        "You can search and open leads; the other tabs and saving changes come back with the CRM."
      )
    : __("You can read this lead; changes can be saved once the CRM is back.");
  return `${saved} ${rest}`;
});
</script>
