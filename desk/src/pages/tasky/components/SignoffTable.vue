<template>
  <!-- a stage's table (modules covered, open items, attendees, deliverables, carry-forward):
       one row a card on a phone, the columns side by side from sm up -->
  <div class="flex flex-col gap-2">
    <p v-if="!rows.length" class="text-p-sm text-ink-gray-6">
      {{ __("No rows yet.") }}
    </p>
    <ol class="flex flex-col gap-2" :aria-label="meta.label">
      <li
        v-for="(row, idx) in rows"
        :key="idx"
        class="flex gap-2 rounded-xl border border-outline-gray-2 bg-surface-base p-3"
      >
        <div
          class="grid min-w-0 flex-1 grid-cols-1 gap-2 sm:grid-cols-[repeat(var(--cols),minmax(0,1fr))]"
          :style="{ '--cols': String(columnNames.length) }"
        >
          <template v-for="column in columnNames" :key="column">
            <Checkbox
              v-if="columns[column].fieldtype === 'Check'"
              class="self-end pb-1.5"
              :label="columns[column].label"
              :model-value="!!row[column]"
              @update:model-value="(v: boolean) => update(idx, column, v ? 1 : 0)"
            />
            <FormControl
              v-else-if="columns[column].fieldtype === 'Select'"
              type="select"
              :label="columns[column].label"
              :options="
                ['', ...(columns[column].options ?? [])].map((o) => ({
                  label: o ? __(o) : '',
                  value: o,
                }))
              "
              :model-value="row[column] ?? ''"
              @update:model-value="(v: string) => update(idx, column, v)"
            />
            <TextInput
              v-else
              :type="inputType(columns[column].fieldtype)"
              :label="columns[column].label"
              :model-value="row[column] ?? ''"
              @update:model-value="(v: string) => update(idx, column, v)"
            />
          </template>
        </div>
        <Button
          variant="ghost"
          class="self-end"
          :aria-label="__('Remove row {0}', String(idx + 1))"
          @click="remove(idx)"
        >
          <template #icon
            ><LucideTrash2 class="size-4" aria-hidden="true"
          /></template>
        </Button>
      </li>
    </ol>
    <Button class="w-fit" :label="__('Add row')" @click="add">
      <template #prefix
        ><LucidePlus class="size-4" aria-hidden="true"
      /></template>
    </Button>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, Checkbox, FormControl, TextInput } from "frappe-ui";
import { computed } from "vue";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
import type { DetailField } from "../useSignoffForm";

const props = defineProps<{
  meta: DetailField;
  modelValue: Record<string, unknown>[] | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [rows: Record<string, unknown>[]];
}>();

const rows = computed(() => props.modelValue ?? []);
const columns = computed(() => props.meta.columns ?? {});
const columnNames = computed(() => Object.keys(columns.value));

function inputType(fieldtype: string) {
  if (fieldtype === "Date") return "date";
  if (["Int", "Float", "Currency", "Percent"].includes(fieldtype))
    return "number";
  return "text";
}

function update(idx: number, column: string, value: unknown) {
  emit(
    "update:modelValue",
    rows.value.map((row, i) => (i === idx ? { ...row, [column]: value } : row))
  );
}
function add() {
  emit("update:modelValue", [
    ...rows.value,
    Object.fromEntries(columnNames.value.map((c) => [c, ""])),
  ]);
}
function remove(idx: number) {
  emit(
    "update:modelValue",
    rows.value.filter((_, i) => i !== idx)
  );
}
</script>
