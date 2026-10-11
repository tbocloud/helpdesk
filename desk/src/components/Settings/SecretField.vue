<template>
  <div class="flex flex-col gap-2">
    <div class="flex flex-col gap-1">
      <label
        :id="labelId"
        :for="inputId"
        class="text-base-medium text-ink-gray-8"
      >
        {{ label }}
      </label>
      <p v-if="description" class="max-w-prose text-p-sm text-ink-gray-6">
        {{ description }}
      </p>
    </div>

    <div
      v-if="status.set && modelValue.mode !== 'replace'"
      class="flex flex-wrap items-center gap-2"
    >
      <span
        :aria-labelledby="labelId"
        class="min-w-0 flex-1 break-all rounded border border-outline-gray-2 bg-surface-gray-1 px-2 py-1.5 font-mono text-sm text-ink-gray-7"
        :class="{ 'line-through': modelValue.mode === 'remove' }"
      >
        {{ status.masked }}
      </span>
      <template v-if="modelValue.mode === 'remove'">
        <span class="text-p-sm text-ink-gray-6">
          {{ __("Removed when you save") }}
        </span>
        <Button :label="__('Undo')" @click="set('keep')" />
      </template>
      <template v-else>
        <Button :label="__('Replace')" @click="replace">
          <template #prefix>
            <LucidePencil class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-if="removable"
          variant="ghost"
          :label="__('Remove')"
          @click="set('remove')"
        />
      </template>
    </div>

    <div v-else class="flex items-center gap-2">
      <FormControl
        :id="inputId"
        :model-value="modelValue.value"
        :type="type"
        class="min-w-0 flex-1"
        :placeholder="placeholder"
        autocomplete="off"
        spellcheck="false"
        @update:model-value="(value: string) => set('replace', value)"
      />
      <Button v-if="status.set" :label="__('Cancel')" @click="set('keep')" />
    </div>

    <ErrorMessage v-if="error" role="alert" :message="error" />
    <slot />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, ErrorMessage, FormControl } from "frappe-ui";
import { nextTick, useId } from "vue";
import LucidePencil from "~icons/lucide/pencil";

export interface SecretStatus {
  set: boolean;
  masked: string;
}

/** keep: leave the saved value; replace: send `value`; remove: clear it on save. */
export interface SecretEdit {
  mode: "keep" | "replace" | "remove";
  value: string;
}

defineProps<{
  label: string;
  description?: string;
  status: SecretStatus;
  modelValue: SecretEdit;
  type?: "text" | "password";
  placeholder?: string;
  removable?: boolean;
  error?: string;
}>();

const emit = defineEmits<{ "update:modelValue": [SecretEdit] }>();

const inputId = `secret-${useId()}`;
const labelId = `${inputId}-label`;

async function replace() {
  set("replace");
  await nextTick();
  document.getElementById(inputId)?.focus();
}

function set(mode: SecretEdit["mode"], value = "") {
  emit("update:modelValue", { mode, value });
}
</script>
