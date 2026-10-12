<template>
  <Dialog
    :open="!!item"
    :title="__('Mark as superseded')"
    :message="item?.label"
    size="lg"
    @update:open="(v: boolean) => !v && emit('update:item', null)"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <p class="text-p-sm text-ink-gray-6">
        {{
          item?.kind === "folder"
            ? __(
                "The folder stays on the project as an older version, and everything in it shows as superseded. It's hidden from the list until someone turns on Show superseded."
              )
            : __(
                "The file stays on the project as an older version. It's hidden from the list until someone turns on Show superseded."
              )
        }}
      </p>
      <div class="flex flex-col gap-1.5">
        <Combobox
          v-model="replacement"
          :label="__('Replaced by (optional)')"
          :options="options"
          :loading="choices.loading"
          :placeholder="
            item?.kind === 'folder'
              ? __('Pick the folder that replaces it')
              : __('Pick the file that replaces it')
          "
          :empty-text="
            item?.kind === 'folder'
              ? __('No other active folder on this project')
              : __('No other active file on this project')
          "
        />
        <p v-if="choices.error" class="text-p-xs text-danger" role="alert">
          {{ errorText(choices.error, __("Couldn't load the choices.")) }}
          <button
            type="button"
            class="rounded underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            @click="choices.reload()"
          >
            {{ __("Retry") }}
          </button>
        </p>
        <button
          v-else-if="replacement"
          type="button"
          class="self-start rounded text-xs text-ink-gray-6 hover:text-ink-gray-8 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          @click="replacement = ''"
        >
          {{ __("No replacement") }}
        </button>
      </div>
      <Textarea
        v-model="note"
        :label="__('Note (optional)')"
        :placeholder="__('e.g. v2 adds the tone rules')"
        :rows="2"
        maxlength="1000"
      />
      <p class="text-p-xs text-ink-gray-5">
        {{ __("The people it's for are told it was replaced.") }}
      </p>

      <div
        v-if="save.error"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{
          errorText(save.error, __("Couldn't change the status."))
        }}</span>
      </div>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Mark as superseded')"
          :loading="save.loading"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  Combobox,
  Dialog,
  Textarea,
  createResource,
  toast,
} from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import type { ItemRef } from "../projectFiles";

const props = defineProps<{
  /** The dialog is open while this is set. */
  item: ItemRef | null;
  projectId: string;
}>();

const emit = defineEmits<{
  "update:item": [value: null];
  saved: [];
}>();

const formId = `supersede-${useId()}`;
const replacement = ref("");
const note = ref("");

const choices = createResource({
  url: "helpdesk.api.project_files.list_replacement_choices",
  makeParams: () => ({
    project: props.projectId,
    kind: props.item?.kind,
    item: props.item?.name,
  }),
  // shown under the picker instead of the global error toast
  onError() {},
});

const options = computed(() =>
  (choices.data ?? []).map(
    (c: { value: string; label: string; path: string }) => ({
      value: c.value,
      label: c.label,
      description: c.path || __("Top level"),
    })
  )
);

const save = createResource({
  url: "helpdesk.api.project_files.set_project_item_status",
  onSuccess() {
    toast.success(__("{0} marked as superseded", props.item?.label ?? ""));
    emit("saved");
    emit("update:item", null);
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});

watch(
  () => props.item,
  (item) => {
    if (!item) return;
    replacement.value = "";
    note.value = "";
    save.reset();
    choices.reload();
  }
);

function submit() {
  if (!props.item || save.loading) return;
  save.submit({
    project: props.projectId,
    kind: props.item.kind,
    item: props.item.name,
    status: "Superseded",
    superseded_by: replacement.value || null,
    note: note.value,
  });
}
</script>
