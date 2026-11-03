<template>
  <div
    v-if="boost.can_spend && actions.length"
    class="flex flex-wrap justify-end gap-2"
  >
    <ErrorMessage :message="error" class="me-auto" />
    <Button
      v-for="a in actions"
      :key="a.method"
      :label="a.label"
      :variant="a.solid ? 'solid' : 'subtle'"
      :theme="a.danger ? 'red' : undefined"
      :loading="busy === a.method"
      @click="a.danger ? (confirm = a) : run(a)"
    />
    <Dialog
      v-model="confirmOpen"
      :options="{ title: confirm?.confirmTitle, size: 'sm' }"
    >
      <template #body-content>
        <p class="text-p-sm text-ink-gray-7">{{ confirm?.confirmText }}</p>
        <FormControl
          v-if="confirm?.method === 'reject'"
          v-model="note"
          class="mt-3"
          type="text"
          :label="__('Reason (optional)')"
        />
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Keep it')" @click="confirm = null" />
          <Button
            theme="red"
            variant="solid"
            :label="confirm?.label"
            :loading="!!confirm && busy === confirm.method"
            @click="confirm && run(confirm)"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  Dialog,
  ErrorMessage,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, ref } from "vue";
import type { Boost } from "../boost";

interface Action {
  method: "approve" | "reject" | "pause" | "resume" | "stop";
  label: string;
  solid?: boolean;
  danger?: boolean;
  confirmTitle?: string;
  confirmText?: string;
}

const props = defineProps<{ boost: Boost }>();
const emit = defineEmits<{ (e: "changed"): void }>();

const busy = ref("");
const error = ref("");
const note = ref("");
const confirm = ref<Action | null>(null);
const confirmOpen = computed({
  get: () => !!confirm.value,
  set: (v) => {
    if (!v) confirm.value = null;
  },
});

const STOP: Action = {
  method: "stop",
  label: __("Stop boost"),
  danger: true,
  confirmTitle: __("Stop this boost?"),
  confirmText: __(
    "It stops for good and can't be turned on again. What it already spent stays."
  ),
};
const actions = computed<Action[]>(() => {
  switch (props.boost.status) {
    case "Pending approval":
      return [
        { method: "approve", label: __("Approve and start"), solid: true },
        {
          method: "reject",
          label: __("Reject"),
          danger: true,
          confirmTitle: __("Reject this boost?"),
          confirmText: __("Nothing is spent. The person who asked is told."),
        },
      ];
    case "Active":
      return [{ method: "pause", label: __("Pause") }, STOP];
    case "Paused":
      return [{ method: "resume", label: __("Resume"), solid: true }, STOP];
    default:
      return [];
  }
});

async function run(action: Action) {
  error.value = "";
  busy.value = action.method;
  try {
    const result = await call(`helpdesk.api.meta_ads.${action.method}`, {
      boost: props.boost.name,
      ...(action.method === "reject" ? { note: note.value } : {}),
    });
    if (result.status === "Failed") toast.error(result.failure_reason);
    confirm.value = null;
    emit("changed");
  } catch (e) {
    error.value = errorText(e, __("That didn't work. Try again."));
  } finally {
    busy.value = "";
  }
}
</script>
