<template>
  <div class="relative">
    <Textarea
      :model-value="modelValue"
      :label="label"
      :placeholder="placeholder"
      :rows="rows"
      :disabled="disabled"
      :maxlength="maxLength"
      role="combobox"
      aria-autocomplete="list"
      :aria-expanded="open"
      :aria-controls="listId"
      :aria-activedescendant="open ? optionId(active) : undefined"
      @update:model-value="(v: string) => emit('update:modelValue', v)"
      @input="onInput"
      @click="onInput"
      @keydown="onKeydown"
      @blur="query = null"
    />
    <ul
      v-show="open"
      :id="listId"
      role="listbox"
      :aria-label="__('People on this project')"
      class="absolute inset-x-0 z-10 mt-1 max-h-52 overflow-y-auto rounded-md border border-outline-gray-2 bg-surface-base py-1 shadow-lg"
    >
      <li
        v-for="(person, i) in matches"
        :id="optionId(i)"
        :key="person.user"
        role="option"
        :aria-selected="i === active"
        class="flex min-h-11 cursor-pointer items-center gap-2 px-3 py-1.5 text-sm md:min-h-0"
        :class="
          i === active
            ? 'bg-surface-gray-2 text-ink-gray-9'
            : 'text-ink-gray-7 hover:bg-surface-gray-1'
        "
        @mousedown.prevent="pick(person)"
      >
        <span class="min-w-0 truncate">{{ person.full_name }}</span>
        <span class="min-w-0 truncate font-mono text-xs text-ink-gray-5">
          {{ person.user }}
        </span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Textarea } from "frappe-ui";
import { computed, nextTick, ref, useId } from "vue";
import type { Person } from "../projectFiles";

/**
 * A plain-text box where "@" suggests people on the project team and inserts
 * "@Full Name". Who was mentioned is read back from the text (mentionedUsers).
 */
const props = withDefaults(
  defineProps<{
    modelValue: string;
    team: Person[];
    label?: string;
    placeholder?: string;
    rows?: number;
    disabled?: boolean;
    maxLength?: number;
  }>(),
  { rows: 3 }
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  /** Ctrl or Cmd + Enter. */
  submit: [];
}>();

const MAX_MATCHES = 6;
const listId = `mentions-${useId()}`;
// the text typed after "@", or null when not suggesting
const query = ref<string | null>(null);
const active = ref(0);
let field: HTMLTextAreaElement | null = null;
let caret = 0;

const matches = computed(() => {
  if (query.value === null) return [];
  const q = query.value.toLowerCase();
  return props.team
    .filter(
      (p) =>
        p.user.toLowerCase().startsWith(q) ||
        p.full_name
          .toLowerCase()
          .split(/\s+/)
          .some((word) => word.startsWith(q))
    )
    .slice(0, MAX_MATCHES);
});
const open = computed(() => matches.value.length > 0);

function optionId(i: number) {
  return `${listId}-${i}`;
}

function onInput(e: Event) {
  field = e.target as HTMLTextAreaElement;
  caret = field.selectionStart ?? field.value.length;
  const found = field.value.slice(0, caret).match(/(?:^|\s)@([^\s@]{0,30})$/);
  query.value = found ? found[1] : null;
  active.value = 0;
}

function onKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    emit("submit");
    return;
  }
  if (!open.value) return;
  const count = matches.value.length;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    active.value =
      (active.value + (e.key === "ArrowDown" ? 1 : -1) + count) % count;
  } else if (e.key === "Enter" || e.key === "Tab") {
    e.preventDefault();
    pick(matches.value[active.value]);
  } else if (e.key === "Escape") {
    // close the list, not the dialog around it
    e.preventDefault();
    e.stopPropagation();
    query.value = null;
  }
}

async function pick(person: Person) {
  const text = props.modelValue;
  const start = caret - (query.value?.length ?? 0) - 1;
  const inserted = `@${person.full_name} `;
  emit(
    "update:modelValue",
    text.slice(0, start) + inserted + text.slice(caret)
  );
  query.value = null;
  await nextTick();
  const at = start + inserted.length;
  field?.focus();
  field?.setSelectionRange(at, at);
}
</script>
