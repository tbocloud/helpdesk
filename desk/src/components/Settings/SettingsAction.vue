<template>
  <div class="flex flex-col items-start gap-1.5">
    <Button
      :label="label"
      :loading="action.loading"
      :disabled="unsaved"
      :tooltip="unsaved ? __('Save your changes first') : ''"
      @click="action.submit()"
    >
      <template #prefix>
        <component :is="icon || LucideSend" class="size-4" aria-hidden="true" />
      </template>
    </Button>
    <div v-if="result" role="status" class="flex flex-col gap-1.5">
      <p
        class="flex items-start gap-1.5 text-p-sm"
        :class="result.ok ? 'text-success' : 'text-danger'"
      >
        <component
          :is="result.ok ? LucideCircleCheck : LucideCircleAlert"
          class="mt-0.5 size-4 shrink-0"
          aria-hidden="true"
        />
        <span>{{ result.message }}</span>
      </p>
      <dl
        v-if="result.details?.length"
        class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-p-sm"
      >
        <template v-for="item in result.details" :key="item.label">
          <dt class="text-ink-gray-6">{{ item.label }}</dt>
          <dd class="break-words font-mono text-ink-gray-8">
            {{ item.value }}
          </dd>
        </template>
      </dl>
    </div>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, createResource } from "frappe-ui";
import { computed, type Component } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideSend from "~icons/lucide/send";

/**
 * A button that runs a whitelisted action on the saved settings (send a test,
 * test a token, request a run) and shows what it returned.
 */
const props = defineProps<{
  /** Dotted path of a POST method returning {ok, message, details?}. */
  method: string;
  params?: Record<string, unknown>;
  label: string;
  icon?: Component;
  /** The action uses the saved settings, so it waits until they are saved. */
  unsaved?: boolean;
}>();

interface ActionResult {
  ok: boolean;
  message: string;
  details?: { label: string; value: string }[];
}

const emit = defineEmits<{ done: [ActionResult] }>();

const action = createResource({
  url: props.method,
  makeParams: () => props.params ?? {},
  onSuccess: (data: ActionResult) => emit("done", data),
});

const result = computed<ActionResult | null>(() => {
  if (action.error)
    return {
      ok: false,
      message: action.error.messages?.[0] || __("Couldn't reach the server"),
    };
  return action.data || null;
});
</script>
