<template>
  <button
    v-if="!people.length && canEdit"
    type="button"
    class="assign-box flex min-h-[52px] min-w-0 items-center gap-2.5 rounded-xl bg-transparent px-3 py-2 text-left transition-colors hover:bg-surface-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
    :aria-label="__('Assign {0}', __(label))"
    @click="emit('assign')"
  >
    <span
      class="grid size-[30px] shrink-0 place-items-center rounded-[8px] bg-brand-soft text-brand"
    >
      <LucidePlus class="size-4" aria-hidden="true" />
    </span>
    <span class="min-w-0">
      <span class="block truncate text-xs text-ink-gray-6">{{
        __(label)
      }}</span>
      <span class="block text-base font-semibold text-brand-ink">{{
        __("Assign")
      }}</span>
    </span>
  </button>

  <div
    v-else-if="!people.length"
    class="flex min-h-[52px] min-w-0 items-center gap-2.5 rounded-xl border border-outline-gray-2 bg-surface-base px-3 py-2"
  >
    <span
      class="grid size-[30px] shrink-0 place-items-center rounded-[8px] bg-surface-gray-2 text-[13px] font-semibold text-ink-gray-5"
      aria-hidden="true"
      >?</span
    >
    <span class="min-w-0">
      <span class="block truncate text-xs text-ink-gray-6">{{
        __(label)
      }}</span>
      <span class="block text-base text-ink-gray-5">{{
        __("Not assigned")
      }}</span>
    </span>
  </div>

  <!-- everyone on the role, each with how far their task is; a button only for
       editors, so people who can't reassign get plain text, not a disabled control -->
  <component
    :is="canEdit ? 'button' : 'div'"
    v-else
    :type="canEdit ? 'button' : undefined"
    class="flex min-h-[52px] min-w-0 flex-col justify-center gap-2.5 rounded-xl border border-outline-gray-2 bg-surface-base px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
    :class="canEdit ? 'hover:bg-surface-gray-1' : ''"
    :title="canEdit ? __('Change who is on this') : undefined"
    @click="canEdit && emit('assign')"
  >
    <span
      v-for="(person, i) in people"
      :key="person.user"
      class="flex min-w-0 items-center gap-3"
    >
      <span class="relative shrink-0">
        <span
          class="grid size-[30px] place-items-center rounded-[8px] text-[13px] font-semibold"
          :class="avatarTone"
          aria-hidden="true"
          >{{ initialOf(person.full_name) }}</span
        >
        <span
          v-if="person.status === 'Completed'"
          class="absolute -bottom-1 -right-1 grid size-3.5 place-items-center rounded-full bg-success text-ink-base shadow-[0_0_0_2px_var(--surface-base)]"
          aria-hidden="true"
        >
          <LucideCheck class="size-2.5" />
        </span>
      </span>
      <span class="min-w-0">
        <span v-if="i === 0" class="block truncate text-xs text-ink-gray-6">{{
          __(label)
        }}</span>
        <span
          class="block truncate text-base font-semibold text-ink-gray-9"
          :title="person.full_name"
          >{{ person.full_name }}</span
        >
        <span
          v-if="person.status || isTaskLate(person)"
          class="block truncate text-xs"
          :class="statusClass(person)"
          :title="person.task"
        >
          <template v-if="person.status">{{
            __(taskStatusMeta(person.status).label)
          }}</template>
          <template v-if="isTaskLate(person)">
            <template v-if="person.status"> · </template>{{ __("late") }}
          </template>
        </span>
      </span>
    </span>
    <!-- the names stay in the accessible name; this says what pressing it does -->
    <span v-if="canEdit" class="sr-only">{{
      __("Change who is on this")
    }}</span>
  </component>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { taskStatusMeta } from "@/pages/tasky/taskMeta";
import { dayjs } from "frappe-ui";
import { computed } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucidePlus from "~icons/lucide/plus";
import type { RolePerson, TeamRole } from "../constants";

const props = defineProps<{
  label: string;
  people: RolePerson[];
  canEdit: boolean;
  role?: TeamRole;
}>();

// full class strings so Tailwind's scanner keeps them; each role keeps its colour across cards
const ROLE_TONES: Record<TeamRole, string> = {
  writer: "bg-brand-soft text-brand-ink",
  designer: "bg-info-soft text-info",
  marketer: "bg-success-soft text-success",
  video_editor: "bg-warning-soft text-warning",
};
const avatarTone = computed(() =>
  props.role ? ROLE_TONES[props.role] : "bg-surface-gray-2 text-ink-gray-7"
);

function initialOf(name: string) {
  return (name || "?").trim().charAt(0).toUpperCase();
}
const emit = defineEmits<{ (e: "assign"): void }>();

function isTaskLate(person: RolePerson) {
  return (
    !!person.due &&
    // an Overdue status already says so
    !["Completed", "Cancelled", "Overdue"].includes(person.status ?? "") &&
    dayjs(person.due).isBefore(dayjs(), "day")
  );
}

function statusClass(person: RolePerson) {
  if (person.status === "Completed") return "text-success";
  if (person.status === "Overdue" || isTaskLate(person)) return "text-danger";
  return "text-ink-gray-6";
}
</script>

<style scoped>
/* the dashed outline takes the card's tone (set on .entry in ContentBoard) */
.assign-box {
  border: 1.5px dashed
    color-mix(in srgb, var(--tone, var(--brand)) 45%, var(--surface-base));
}
</style>
