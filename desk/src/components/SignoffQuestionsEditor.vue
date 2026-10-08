<template>
  <div class="flex flex-col gap-3">
    <p v-if="!modelValue.length" class="text-p-sm text-ink-gray-6">
      {{ __("No questions yet. Add the first one below.") }}
    </p>
    <ol class="flex flex-col gap-2" :aria-label="__('Questions')">
      <li
        v-for="(row, idx) in modelValue"
        :key="keys[idx]"
        class="flex gap-3 rounded-lg border border-outline-gray-2 bg-surface-base p-3"
      >
        <span
          class="w-5 shrink-0 pt-1.5 text-right font-mono text-xs tabular-nums text-ink-gray-5"
          aria-hidden="true"
          >{{ idx + 1 }}</span
        >
        <div class="flex min-w-0 flex-1 flex-col gap-2">
          <div
            class="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]"
          >
            <TextInput
              :model-value="row.section"
              :label="__('Section')"
              :placeholder="__('e.g. Sales')"
              :list="listId"
              autocomplete="off"
              maxlength="140"
              @update:model-value="(v: string) => update(idx, { section: v })"
            />
            <TextInput
              :model-value="row.help_text"
              :label="__('Help text (optional)')"
              :placeholder="__('Shown under the question')"
              @update:model-value="(v: string) => update(idx, { help_text: v })"
            />
          </div>
          <FormControl
            type="textarea"
            :model-value="row.question"
            :label="__('Question {0}', String(idx + 1))"
            :placeholder="
              __('e.g. I can record a Payment Entry against an invoice.')
            "
            :rows="2"
            @update:model-value="(v: string) => update(idx, { question: v })"
          />
          <p
            v-if="row.response && row.response !== 'Pending'"
            class="text-p-xs text-ink-gray-5"
          >
            {{
              __(
                "The customer answered {0}. Rewording the question resets it to Pending.",
                __(row.response)
              )
            }}
          </p>
        </div>
        <div class="flex shrink-0 flex-col gap-0.5">
          <Button
            variant="ghost"
            :tooltip="__('Move up')"
            :aria-label="__('Move question {0} up', String(idx + 1))"
            :disabled="idx === 0"
            @click="move(idx, -1)"
          >
            <template #icon>
              <LucideArrowUp class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <Button
            variant="ghost"
            :tooltip="__('Move down')"
            :aria-label="__('Move question {0} down', String(idx + 1))"
            :disabled="idx === modelValue.length - 1"
            @click="move(idx, 1)"
          >
            <template #icon>
              <LucideArrowDown class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <Button
            variant="ghost"
            :tooltip="__('Remove')"
            :aria-label="__('Remove question {0}', String(idx + 1))"
            @click="remove(idx)"
          >
            <template #icon>
              <LucideTrash2 class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
      </li>
    </ol>
    <datalist :id="listId">
      <option v-for="s in sections" :key="s" :value="s" />
    </datalist>
    <div>
      <Button :label="__('Add question')" @click="add">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SignoffQuestion } from "@/pages/tasky/signoffMeta";
import { __ } from "@/translation";
import { Button, FormControl, TextInput } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideArrowDown from "~icons/lucide/arrow-down";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";

const props = defineProps<{ modelValue: SignoffQuestion[] }>();
const emit = defineEmits<{ "update:modelValue": [value: SignoffQuestion[]] }>();

const listId = `signoff-sections-${useId()}`;

// stable keys for rows that have no name yet, so reordering keeps focus and input state
let nextKey = 0;
const keys = ref<string[]>([]);
watch(
  () => props.modelValue.length,
  (length) => {
    while (keys.value.length < length) keys.value.push(`k${nextKey++}`);
    keys.value.length = length;
  },
  { immediate: true }
);

const sections = computed(() => [
  ...new Set(props.modelValue.map((r) => r.section).filter(Boolean)),
]);

function update(idx: number, patch: Partial<SignoffQuestion>) {
  const rows = [...props.modelValue];
  rows[idx] = { ...rows[idx], ...patch };
  emit("update:modelValue", rows);
}

function move(idx: number, by: number) {
  const rows = [...props.modelValue];
  const [row] = rows.splice(idx, 1);
  rows.splice(idx + by, 0, row);
  const [key] = keys.value.splice(idx, 1);
  keys.value.splice(idx + by, 0, key);
  emit("update:modelValue", rows);
}

function remove(idx: number) {
  keys.value.splice(idx, 1);
  emit(
    "update:modelValue",
    props.modelValue.filter((_, i) => i !== idx)
  );
}

function add() {
  const last = props.modelValue[props.modelValue.length - 1];
  emit("update:modelValue", [
    ...props.modelValue,
    { section: last?.section || "", question: "", help_text: "" },
  ]);
}
</script>
