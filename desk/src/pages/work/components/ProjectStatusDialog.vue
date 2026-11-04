<template>
  <Dialog
    v-model:open="open"
    :title="__('Update status: {0}', row?.project_name ?? '')"
    size="lg"
  >
    <form
      v-if="draft && row"
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <p class="text-p-sm text-ink-gray-6">
        {{
          row.update_age === null
            ? __("This project has no status update yet.")
            : __(
                "Starts from the last update, written {0} day(s) ago. Saving adds a new one; the old ones stay in the history.",
                String(row.update_age)
              )
        }}
      </p>
      <ProjectStatusFields
        v-model="draft"
        :stages="stages"
        :waiting-on="waitingOn"
      />
      <p
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{ errorMessage }}
      </p>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Save update')"
          :loading="save.loading"
          :disabled="!draft?.stage || save.loading"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, Dialog, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import {
  blankDraft,
  type StatusDraft,
  type StatusRow,
} from "../projectStatusMeta";
import ProjectStatusFields from "./ProjectStatusFields.vue";

const props = defineProps<{
  row: StatusRow | null;
  stages: string[];
  waitingOn: string[];
}>();
const emit = defineEmits<{ saved: [] }>();
const open = defineModel<boolean>("open", { default: false });

const formId = `project-status-${useId()}`;
const draft = ref<StatusDraft | null>(null);

watch(open, (isOpen) => {
  if (!isOpen || !props.row) return;
  draft.value = blankDraft(props.row);
  save.reset();
});

const save = createResource({
  url: "helpdesk.api.project_status.save_status_updates",
  onSuccess() {
    toast.success(__("Status saved"));
    open.value = false;
    emit("saved");
  },
  // shown inline instead of the global error toast
  onError() {},
});

const errorMessage = computed(() =>
  errorText(save.error, __("Couldn't save the update."))
);

function submit() {
  if (!draft.value?.stage || save.loading) return;
  save.submit({ updates: [draft.value] });
}
</script>
