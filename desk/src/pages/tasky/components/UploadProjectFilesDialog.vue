<template>
  <Dialog
    :open="open"
    :title="__('Add files')"
    size="lg"
    :dismissible="!uploading"
    @update:open="onOpenChange"
  >
    <div class="flex flex-col gap-4">
      <div
        class="flex flex-col items-center gap-2 rounded-lg border border-dashed px-4 py-6 text-center transition-colors"
        :class="
          dragging
            ? 'border-brand bg-brand-soft'
            : 'border-outline-gray-3 bg-surface-gray-1'
        "
        @dragover.prevent="dragging = true"
        @dragleave.self="dragging = false"
        @drop.prevent="onDrop"
      >
        <LucideUpload class="size-5 text-ink-gray-5" aria-hidden="true" />
        <p class="text-p-sm text-ink-gray-6">
          {{ __("Drop files here, or") }}
          <button
            type="button"
            class="rounded font-medium text-ink-gray-9 underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            :disabled="uploading"
            @click="fileInput?.click()"
          >
            {{ __("choose files") }}
          </button>
        </p>
        <p class="text-p-xs text-ink-gray-5">
          {{
            __(
              "Markdown, PDFs, images or any other file, up to {0} each. Only people on the project can open them.",
              formatBytes(maxFileSize)
            )
          }}
        </p>
        <input
          ref="fileInput"
          type="file"
          multiple
          class="sr-only"
          tabindex="-1"
          :aria-label="__('Choose files')"
          @change="onPick"
        />
      </div>

      <ul v-if="queue.length" class="flex flex-col gap-1.5" role="list">
        <li
          v-for="(item, i) in queue"
          :key="i"
          class="flex items-center gap-2 rounded-md border border-outline-gray-2 px-3 py-2 text-sm"
        >
          <component
            :is="fileIcon(item.file.name)"
            class="size-4 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          <span class="min-w-0 flex-1 truncate text-ink-gray-8">
            {{ item.file.name }}
          </span>
          <span class="shrink-0 font-mono text-xs tabular-nums text-ink-gray-5">
            {{ formatBytes(item.file.size) }}
          </span>
          <span
            v-if="item.state === 'done'"
            class="flex shrink-0 items-center gap-1 text-xs text-success"
          >
            <LucideCheck class="size-3.5" aria-hidden="true" />
            {{ __("Added") }}
          </span>
          <span
            v-else-if="item.state === 'uploading'"
            class="flex shrink-0 items-center gap-1 text-xs text-ink-gray-6"
          >
            <LucideLoaderCircle
              class="size-3.5 animate-spin"
              aria-hidden="true"
            />
            {{ __("Uploading") }}
          </span>
          <button
            v-else-if="!uploading && item.state !== 'error'"
            type="button"
            class="grid size-6 shrink-0 place-items-center rounded text-ink-gray-5 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            :aria-label="__('Remove {0}', item.file.name)"
            @click="queue.splice(i, 1)"
          >
            <LucideX class="size-3.5" aria-hidden="true" />
          </button>
          <p
            v-if="item.error"
            class="basis-full text-p-xs text-danger"
            role="alert"
          >
            {{ item.error }}
          </p>
        </li>
      </ul>

      <FileForPicker v-model="forUsers" :team="team" />
    </div>

    <template #actions>
      <div class="flex items-center justify-end gap-2">
        <span
          v-if="uploading"
          class="mr-auto text-p-sm text-ink-gray-6"
          aria-live="polite"
        >
          {{
            __("Uploading {0} of {1}", String(doneCount + 1), String(pending))
          }}
        </span>
        <Button
          :label="__('Close')"
          :disabled="uploading"
          @click="onOpenChange(false)"
        />
        <Button
          variant="solid"
          :label="
            readyCount > 1
              ? __('Upload {0} files', String(readyCount))
              : __('Upload')
          "
          :loading="uploading"
          :disabled="!readyCount"
          @click="uploadAll"
        >
          <template #prefix>
            <LucideUpload class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, Dialog, FileUploadHandler, toast } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucideUpload from "~icons/lucide/upload";
import LucideX from "~icons/lucide/x";
import { fileIcon, formatBytes, type Person } from "../projectFiles";
import FileForPicker from "./FileForPicker.vue";

interface QueuedFile {
  file: File;
  state: "ready" | "uploading" | "done" | "error";
  error?: string;
}

const props = defineProps<{
  open: boolean;
  projectId: string;
  team: Person[];
  /** The site's upload limit in bytes. */
  maxFileSize: number;
  /** Files dropped on the page before the dialog opened. */
  initialFiles?: File[];
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  uploaded: [];
}>();

const fileInput = ref<HTMLInputElement | null>(null);
const queue = ref<QueuedFile[]>([]);
const forUsers = ref<string[]>([]);
const dragging = ref(false);
const uploading = ref(false);

const readyCount = computed(
  () => queue.value.filter((q) => q.state === "ready").length
);
const doneCount = ref(0);
const pending = ref(0);

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return;
    queue.value = [];
    forUsers.value = [];
    addFiles(props.initialFiles ?? []);
  },
  { immediate: true }
);

/** Queue files for upload, flagging any over the site's size limit as an error. */
function addFiles(files: File[]) {
  for (const file of files) {
    const tooBig = props.maxFileSize && file.size > props.maxFileSize;
    queue.value.push({
      file,
      state: tooBig ? "error" : "ready",
      error: tooBig
        ? __(
            "This file is {0}; the limit is {1}.",
            formatBytes(file.size),
            formatBytes(props.maxFileSize)
          )
        : undefined,
    });
  }
}

/** Queue the files chosen via the file input, then clear it so the same file can be re-picked. */
function onPick(e: Event) {
  const input = e.target as HTMLInputElement;
  addFiles([...(input.files ?? [])]);
  input.value = "";
}

/** Queue the files dropped on the dialog. */
function onDrop(e: DragEvent) {
  dragging.value = false;
  if (uploading.value) return;
  addFiles([...(e.dataTransfer?.files ?? [])]);
}

/** The upload endpoint URL for this project and the chosen "for" list. */
function uploadUrl() {
  const params = new URLSearchParams({
    project: props.projectId,
    for_users: JSON.stringify(forUsers.value),
  });
  return `/api/method/helpdesk.api.project_files.upload_project_file?${params}`;
}

/** Upload the queued files one at a time, so a failed file is reported by name and the rest still upload. */
async function uploadAll() {
  const ready = queue.value.filter((q) => q.state === "ready");
  if (!ready.length || uploading.value) return;
  uploading.value = true;
  doneCount.value = 0;
  pending.value = ready.length;
  let added = 0;
  for (const item of ready) {
    item.state = "uploading";
    try {
      await new FileUploadHandler().upload(item.file, {
        upload_endpoint: uploadUrl(),
        private: true,
      });
      item.state = "done";
      added++;
    } catch (e: any) {
      item.state = "error";
      item.error = e?.message || __("Couldn't upload this file.");
    }
    doneCount.value++;
  }
  uploading.value = false;
  if (added) {
    emit("uploaded");
    toast.success(
      added === 1 ? __("1 file added") : __("{0} files added", String(added))
    );
  }
  // keep the dialog open while something failed, so the reason stays readable
  if (queue.value.every((q) => q.state === "done")) emit("update:open", false);
}

/** Close the dialog, unless an upload is still in progress. */
function onOpenChange(value: boolean) {
  if (!value && uploading.value) return;
  emit("update:open", value);
}
</script>
