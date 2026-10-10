<template>
  <DefinePeople>
    <span class="block truncate text-xs text-ink-gray-6">{{ __(label) }}</span>
    <span class="mt-1 flex flex-col gap-2">
      <span
        v-for="person in people"
        :key="person.user"
        class="flex min-w-0 items-center gap-2.5"
      >
        <span
          class="relative grid size-7 shrink-0 place-items-center rounded-full bg-surface-gray-2 text-xs font-semibold text-ink-gray-7"
          aria-hidden="true"
        >
          {{ initialOf(person.full_name) }}
          <span
            v-if="person.status === 'Completed'"
            class="absolute -bottom-0.5 -right-0.5 grid size-3.5 place-items-center rounded-full bg-success text-ink-base ring-2 ring-surface-base"
          >
            <LucideCheck class="size-2.5" />
          </span>
        </span>
        <span class="min-w-0 flex-1">
          <span
            class="block truncate text-sm font-semibold text-ink-gray-9"
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
    </span>
  </DefinePeople>

  <button
    v-if="!people.length && canEdit"
    type="button"
    :class="[
      BOX,
      'border-dashed border-outline-gray-3 hover:bg-surface-gray-1',
    ]"
    :aria-label="__('Assign {0}', __(label))"
    @click="emit('assign')"
  >
    <span class="block truncate text-xs text-ink-gray-6">{{ __(label) }}</span>
    <span
      class="mt-1 flex items-center gap-1.5 text-sm font-medium text-ink-gray-8"
    >
      <LucidePlus class="size-4 text-ink-gray-6" aria-hidden="true" />
      {{ __("Assign") }}
    </span>
  </button>

  <div v-else-if="!people.length" :class="[BOX, 'border-outline-gray-2']">
    <span class="block truncate text-xs text-ink-gray-6">{{ __(label) }}</span>
    <span class="mt-1 block text-sm text-ink-gray-5">{{
      __("Not assigned")
    }}</span>
  </div>

  <!-- everyone on the role, each with how far their task is; a button only for
       editors, so people who can't reassign get plain text, not a disabled control.
       Not <component :is="'button'">: that resolves to frappe-ui's global Button,
       whose fixed height clipped the names. -->
  <button
    v-else-if="canEdit"
    type="button"
    :class="[BOX, 'border-outline-gray-2 hover:bg-surface-gray-1']"
    :title="__('Change who is on this')"
    @click="emit('assign')"
  >
    <ReusePeople />
    <!-- the names stay in the accessible name; this says what pressing it does -->
    <span class="sr-only">{{ __("Change who is on this") }}</span>
  </button>

  <div v-else :class="[BOX, 'border-outline-gray-2']">
    <ReusePeople />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { taskStatusMeta } from "@/pages/tasky/taskMeta";
import { createReusableTemplate } from "@vueuse/core";
import { dayjs } from "frappe-ui";
import LucideCheck from "~icons/lucide/check";
import LucidePlus from "~icons/lucide/plus";
import type { RolePerson } from "../constants";

defineProps<{
  label: string;
  people: RolePerson[];
  canEdit: boolean;
}>();
const emit = defineEmits<{ (e: "assign"): void }>();

const [DefinePeople, ReusePeople] = createReusableTemplate();

const BOX =
  "block min-w-0 rounded-lg border bg-surface-base px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4";

function initialOf(name: string) {
  return (name || "?").trim().charAt(0).toUpperCase();
}

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
