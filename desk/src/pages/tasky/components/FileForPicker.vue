<template>
  <fieldset class="flex flex-col gap-1.5">
    <legend class="mb-1.5 text-xs text-ink-gray-5">
      {{ __("For") }}
      <span class="text-ink-gray-4">{{ __("(optional)") }}</span>
    </legend>
    <p v-if="!team.length" class="text-p-sm text-ink-gray-5">
      {{ __("No one is on this project yet.") }}
    </p>
    <div v-else class="grid max-h-48 gap-1 overflow-y-auto sm:grid-cols-2">
      <label
        v-for="person in team"
        :key="person.user"
        class="flex cursor-pointer items-center gap-2.5 rounded-md border px-3 py-2 text-sm transition-colors focus-within:ring-2 focus-within:ring-outline-gray-4"
        :class="
          modelValue.includes(person.user)
            ? 'border-outline-gray-4 bg-surface-gray-1 text-ink-gray-9'
            : 'border-outline-gray-2 text-ink-gray-7 hover:border-outline-gray-3'
        "
      >
        <input
          type="checkbox"
          class="size-4 shrink-0 rounded accent-brand focus:outline-none"
          :checked="modelValue.includes(person.user)"
          @change="toggle(person.user)"
        />
        <span class="truncate">{{ person.full_name }}</span>
        <span v-if="person.user === me" class="text-xs text-ink-gray-5">
          {{ __("(you)") }}
        </span>
      </label>
    </div>
    <p class="text-p-xs text-ink-gray-5">
      {{
        __(
          "They get a notification. Everyone on the project can still see the file."
        )
      }}
    </p>
  </fieldset>
</template>

<script setup lang="ts">
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { computed } from "vue";
import type { Person } from "../projectFiles";

const props = defineProps<{
  modelValue: string[];
  /** The project's members and lead. */
  team: Person[];
}>();

const emit = defineEmits<{ "update:modelValue": [value: string[]] }>();

const me = computed(() => useAuthStore().userId);

function toggle(user: string) {
  emit(
    "update:modelValue",
    props.modelValue.includes(user)
      ? props.modelValue.filter((u) => u !== user)
      : [...props.modelValue, user]
  );
}
</script>
