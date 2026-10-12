<template>
  <Dialog
    :open="open"
    :title="
      folder
        ? __('Rename folder')
        : parent
        ? __('New folder in {0}', parent.folder_name)
        : __('New folder')
    "
    size="lg"
    @update:open="(v: boolean) => emit('update:open', v)"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <TextInput
        v-model="name"
        :label="__('Name')"
        :placeholder="__('e.g. Prompts')"
        maxlength="140"
        required
      />
      <Textarea
        v-model="description"
        :label="__('Description')"
        :placeholder="__('Optional: what goes in this folder')"
        :rows="2"
      />
      <FileForPicker v-if="!folder" v-model="forUsers" :team="team" folder />

      <div
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ errorMessage }}</span>
      </div>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="folder ? __('Save changes') : __('Create folder')"
          :loading="save.loading"
          :disabled="!name.trim()"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, Dialog, Textarea, TextInput, createResource } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import type { Person, ProjectFolder } from "../projectFiles";
import FileForPicker from "./FileForPicker.vue";

const props = defineProps<{
  open: boolean;
  projectId: string;
  team: Person[];
  /** The folder to rename; a new folder when empty. */
  folder?: ProjectFolder | null;
  /** Where a new folder goes: inside this folder, or the top level when empty. */
  parent?: ProjectFolder | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  saved: [folder: { name: string; folder_name: string }];
}>();

const formId = `project-folder-${useId()}`;
const name = ref("");
const description = ref("");
const forUsers = ref<string[]>([]);

const handlers = {
  onSuccess(data: { name: string; folder_name: string }) {
    emit("saved", data);
    emit("update:open", false);
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
};
const create = createResource({
  url: "helpdesk.api.project_files.create_project_folder",
  ...handlers,
});
const rename = createResource({
  url: "helpdesk.api.project_files.update_project_folder",
  ...handlers,
});
const save = computed(() => (props.folder ? rename : create));

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return;
    name.value = props.folder?.folder_name ?? "";
    description.value = props.folder?.description ?? "";
    forUsers.value = [];
    create.reset();
    rename.reset();
  },
  { immediate: true }
);

const errorMessage = computed(() =>
  save.value.error
    ? errorText(
        save.value.error,
        props.folder
          ? __("Couldn't save the folder.")
          : __("Couldn't create the folder.")
      )
    : ""
);

function submit() {
  if (!name.value.trim() || save.value.loading) return;
  save.value.submit(
    props.folder
      ? {
          project: props.projectId,
          folder: props.folder.name,
          folder_name: name.value,
          description: description.value,
        }
      : {
          project: props.projectId,
          folder_name: name.value,
          description: description.value,
          for_users: forUsers.value,
          parent_folder: props.parent?.name ?? null,
        }
  );
}
</script>
