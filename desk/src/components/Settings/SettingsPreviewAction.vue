<template>
  <div class="flex w-full flex-col items-start gap-3">
    <div class="flex flex-wrap items-center gap-2">
      <Button
        :label="previewLabel"
        :loading="preview.loading"
        :disabled="unsaved || apply.loading"
        :tooltip="unsaved ? __('Save your changes first') : ''"
        @click="runPreview"
      >
        <template #prefix>
          <LucideEye class="size-4" aria-hidden="true" />
        </template>
      </Button>
      <Button
        v-if="rows.length && !applied"
        :label="applyLabel(rows.length)"
        :loading="apply.loading"
        :disabled="unsaved || preview.loading"
        @click="apply.submit()"
      >
        <template #prefix>
          <LucideCheck class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
    <p v-if="unsaved" class="text-p-xs text-ink-gray-5">
      {{ __("Save your changes first: this uses the saved settings.") }}
    </p>
    <p
      v-if="status"
      role="status"
      class="flex items-start gap-1.5 text-p-sm"
      :class="status.ok ? 'text-ink-gray-7' : 'text-danger'"
    >
      <component
        :is="status.ok ? LucideCircleCheck : LucideCircleAlert"
        class="mt-0.5 size-4 shrink-0"
        :class="status.ok ? 'text-success' : 'text-danger'"
        aria-hidden="true"
      />
      <span class="min-w-0 break-words">{{ status.message }}</span>
    </p>
    <ul
      v-if="rows.length"
      class="w-full divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2"
      :aria-label="listLabel"
    >
      <li v-for="(row, index) in rows" :key="index" class="min-w-0 px-3 py-2">
        <slot name="row" :row="row" />
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts" generic="Row">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource } from "frappe-ui";
import { computed, ref } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideEye from "~icons/lucide/eye";

/**
 * A one-off change with a dry run: Preview lists what would change, nothing is
 * written until Apply, and Apply is only offered after a preview with rows.
 */
const props = defineProps<{
  previewMethod: string;
  previewParams?: Record<string, unknown>;
  applyMethod: string;
  applyParams?: Record<string, unknown>;
  previewLabel: string;
  /** the Apply button's label for this many rows, e.g. "Apply to 12 tickets" */
  applyLabel: (count: number) => string;
  /** the list's accessible name */
  listLabel: string;
  /** the rows a response carries */
  rowsOf: (data: any) => Row[];
  /** one line on a response, preview or apply */
  summarize: (data: any, applied: boolean) => { ok: boolean; message: string };
  /** the action uses the saved settings */
  unsaved?: boolean;
}>();

const emit = defineEmits<{ applied: [] }>();

const applied = ref(false);
const result = ref<{ data: any; applied: boolean } | null>(null);

const preview = createResource({
  url: props.previewMethod,
  makeParams: () => props.previewParams ?? {},
  onSuccess(data: unknown) {
    applied.value = false;
    result.value = { data, applied: false };
  },
});

const apply = createResource({
  url: props.applyMethod,
  makeParams: () => props.applyParams ?? {},
  onSuccess(data: unknown) {
    applied.value = true;
    result.value = { data, applied: true };
    emit("applied");
  },
});

function runPreview() {
  result.value = null;
  preview.submit();
}

const rows = computed<Row[]>(() =>
  result.value && !result.value.applied ? props.rowsOf(result.value.data) : []
);

const status = computed(() => {
  const error = apply.error || preview.error;
  if (error)
    return {
      ok: false,
      message: errorText(error, __("Couldn't reach the server. Try again.")),
    };
  if (!result.value) return null;
  return props.summarize(result.value.data, result.value.applied);
});
</script>
