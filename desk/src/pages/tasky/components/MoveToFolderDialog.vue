<template>
  <Dialog
    :open="!!item"
    :title="__('Move to folder')"
    :message="item?.label"
    size="md"
    @update:open="(v: boolean) => !v && emit('update:item', null)"
  >
    <form :id="formId" novalidate @submit.prevent="submit">
      <fieldset class="flex flex-col gap-1.5">
        <legend class="mb-1.5 text-xs text-ink-gray-5">
          {{ __("Where should it go?") }}
        </legend>
        <div
          class="flex max-h-80 flex-col gap-1 overflow-y-auto"
          role="presentation"
        >
          <label
            v-for="option in options"
            :key="option.value"
            class="flex cursor-pointer items-center gap-2 rounded-md border py-2 pr-3 text-sm transition-colors focus-within:ring-2 focus-within:ring-outline-gray-4"
            :style="{ paddingLeft: `${12 + option.indent * 16}px` }"
            :class="
              target === option.value
                ? 'border-outline-gray-4 bg-surface-gray-1 text-ink-gray-9'
                : 'border-outline-gray-2 text-ink-gray-7 hover:border-outline-gray-3'
            "
          >
            <input
              v-model="target"
              type="radio"
              :name="`${formId}-folder`"
              :value="option.value"
              class="size-4 shrink-0 accent-brand focus:outline-none"
            />
            <component
              :is="option.value ? LucideFolder : LucideFiles"
              class="size-4 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
            <span class="min-w-0 flex-1 truncate">{{ option.label }}</span>
            <span
              v-if="option.value === current"
              class="shrink-0 text-xs text-ink-gray-5"
            >
              {{ __("(here now)") }}
            </span>
          </label>
        </div>
        <p v-if="item?.kind === 'folder'" class="text-p-xs text-ink-gray-5">
          {{
            __(
              "Everything in it moves too. Folders go at most {0} levels deep, so deeper places aren't listed.",
              String(maxDepth)
            )
          }}
        </p>
      </fieldset>

      <div
        v-if="move.error"
        role="alert"
        class="mt-4 flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ errorText(move.error, __("Couldn't move it.")) }}</span>
      </div>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="item?.kind === 'folder' ? __('Move folder') : __('Move file')"
          :loading="move.loading"
          :disabled="target === current"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, Dialog, createResource, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFiles from "~icons/lucide/files";
import LucideFolder from "~icons/lucide/folder";
import { subtree, type MoveItem, type ProjectFolder } from "../projectFiles";

const props = defineProps<{
  /** The dialog is open while this is set. */
  item: MoveItem | null;
  projectId: string;
  /** Every folder, parents before their subfolders. */
  folders: ProjectFolder[];
  maxDepth: number;
}>();

const emit = defineEmits<{
  "update:item": [value: null];
  moved: [];
}>();

const formId = `move-to-folder-${useId()}`;
// "" is the top level of the project's files
const target = ref("");
const current = computed(() => props.item?.current ?? "");

const options = computed(() => {
  const item = props.item;
  const blocked =
    item?.kind === "folder" ? subtree(props.folders, item.name) : new Set();
  const height = item?.kind === "folder" ? item.height ?? 1 : 0;
  return [
    { value: "", label: __("Files (top level)"), indent: 0 },
    ...props.folders
      .filter((f) => !blocked.has(f.name) && f.depth + height <= props.maxDepth)
      .map((f) => ({ value: f.name, label: f.folder_name, indent: f.depth })),
  ];
});

const handlers = {
  onSuccess() {
    const folder = props.folders.find((f) => f.name === target.value);
    toast.success(
      folder
        ? __("Moved to {0}", folder.folder_name)
        : __("Moved to the top level")
    );
    emit("moved");
    emit("update:item", null);
  },

  // shown inline in the dialog instead of the global error toast
  onError() {},
};
const moveFile = createResource({
  url: "helpdesk.api.project_files.move_project_file",
  ...handlers,
});
const moveFolder = createResource({
  url: "helpdesk.api.project_files.move_project_folder",
  ...handlers,
});
const move = computed(() =>
  props.item?.kind === "folder" ? moveFolder : moveFile
);

watch(
  () => props.item?.name,
  (name) => {
    if (!name) return;
    target.value = current.value;
    moveFile.reset();
    moveFolder.reset();
  },
  { immediate: true }
);

function submit() {
  const item = props.item;
  if (!item || target.value === current.value || move.value.loading) return;
  move.value.submit(
    item.kind === "folder"
      ? {
          project: props.projectId,
          folder: item.name,
          parent_folder: target.value || null,
        }
      : {
          project: props.projectId,
          file: item.name,
          folder: target.value || null,
        }
  );
}
</script>
