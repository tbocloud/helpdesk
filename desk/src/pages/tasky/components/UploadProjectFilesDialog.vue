<template>
  <Dialog
    :open="open"
    :title="
      folder ? __('Add files to {0}', folder.folder_name) : __('Add files')
    "
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
          {{ __("Drop files or whole folders here") }}
        </p>
        <div class="flex flex-wrap justify-center gap-2">
          <Button
            :label="__('Choose files')"
            :disabled="uploading"
            @click="fileInput?.click()"
          >
            <template #prefix>
              <LucideFiles class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <Button
            :label="__('Upload folder')"
            :disabled="uploading"
            @click="folderInput?.click()"
          >
            <template #prefix>
              <LucideFolderUp class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
        <p class="text-p-xs text-ink-gray-5">
          {{
            __(
              "Any file up to {0} each, {1} files at a time. A folder keeps its subfolders; hidden files are skipped. Only people on the project can open them.",
              formatBytes(maxFileSize),
              String(maxUploadFiles)
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
        <input
          ref="folderInput"
          type="file"
          webkitdirectory
          class="sr-only"
          tabindex="-1"
          :aria-label="__('Choose a folder')"
          @change="onPick"
        />
      </div>

      <p
        v-if="skipped"
        class="flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-p-sm text-warning"
        role="status"
      >
        <LucideTriangleAlert
          class="mt-0.5 size-4 shrink-0"
          aria-hidden="true"
        />
        {{
          __(
            "{0} more files were left out: one upload takes at most {1}. Add them in another upload.",
            String(skipped),
            String(maxUploadFiles)
          )
        }}
      </p>

      <ul
        v-if="queue.length"
        class="flex max-h-72 flex-col gap-1.5 overflow-y-auto"
        role="list"
      >
        <li
          v-for="(item, i) in queue"
          :key="i"
          class="flex flex-wrap items-center gap-2 rounded-md border border-outline-gray-2 px-3 py-2 text-sm"
        >
          <component
            :is="fileIcon(item.file.name)"
            class="size-4 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          <span
            class="min-w-0 flex-1 truncate text-ink-gray-8"
            :title="label(item)"
          >
            <span v-if="item.dir" class="text-ink-gray-5">{{ item.dir }}/</span
            >{{ item.file.name }}
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
            :aria-label="__('Remove {0}', label(item))"
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
            creatingFolders
              ? __("Creating folders…")
              : __(
                  "Uploading {0} of {1}",
                  String(Math.min(doneCount + 1, pending)),
                  String(pending)
                )
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
import { errorText } from "@/utils";
import { Button, Dialog, FileUploadHandler, call, toast } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucideFiles from "~icons/lucide/files";
import LucideFolderUp from "~icons/lucide/folder-up";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUpload from "~icons/lucide/upload";
import LucideX from "~icons/lucide/x";
import {
  fileIcon,
  formatBytes,
  fromDataTransfer,
  fromFileList,
  type Person,
  type ProjectFolder,
  type UploadItem,
} from "../projectFiles";
import FileForPicker from "./FileForPicker.vue";

interface QueuedFile extends UploadItem {
  state: "ready" | "uploading" | "done" | "error";
  error?: string;
}

const props = defineProps<{
  open: boolean;
  projectId: string;
  team: Person[];
  /** The site's upload limit in bytes. */
  maxFileSize: number;
  /** Most files one upload takes. */
  maxUploadFiles: number;
  /** Files and folders dropped on the page before the dialog opened. */
  initialFiles?: UploadItem[];
  /** The folder the upload goes into; the top level when empty. */
  folder?: ProjectFolder | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  uploaded: [];
}>();

const fileInput = ref<HTMLInputElement | null>(null);
const folderInput = ref<HTMLInputElement | null>(null);
const queue = ref<QueuedFile[]>([]);
const forUsers = ref<string[]>([]);
const dragging = ref(false);
const uploading = ref(false);
const creatingFolders = ref(false);
const skipped = ref(0);

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
    skipped.value = 0;
    addFiles(props.initialFiles ?? []);
  },
  { immediate: true }
);

function label(item: UploadItem) {
  return item.dir ? `${item.dir}/${item.file.name}` : item.file.name;
}

function addFiles(items: UploadItem[]) {
  const room = Math.max(props.maxUploadFiles - queue.value.length, 0);
  skipped.value += Math.max(items.length - room, 0);
  for (const { file, dir } of items.slice(0, room)) {
    const tooBig = props.maxFileSize && file.size > props.maxFileSize;
    queue.value.push({
      file,
      dir,
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

function onPick(e: Event) {
  const input = e.target as HTMLInputElement;
  addFiles(fromFileList(input.files ?? []));
  input.value = "";
}

async function onDrop(e: DragEvent) {
  dragging.value = false;
  if (uploading.value || !e.dataTransfer) return;
  addFiles(await fromDataTransfer(e.dataTransfer));
}

function uploadUrl(folder: string | null) {
  const params = new URLSearchParams({
    project: props.projectId,
    for_users: JSON.stringify(forUsers.value),
  });
  if (folder) params.set("folder", folder);
  return `/api/method/helpdesk.api.project_files.upload_project_file?${params}`;
}

/** Recreates the picked folders inside the current one: {path: folder}. */
async function makeFolders(ready: QueuedFile[]) {
  const paths = [...new Set(ready.map((q) => q.dir).filter(Boolean))];
  if (!paths.length) return {};
  creatingFolders.value = true;
  try {
    return (await call("helpdesk.api.project_files.create_folder_paths", {
      project: props.projectId,
      paths,
      parent_folder: props.folder?.name ?? null,
    })) as Record<string, string>;
  } catch (e) {
    const message = errorText(e, __("Couldn't create the folders."));
    for (const item of ready)
      if (item.dir) Object.assign(item, { state: "error", error: message });
    return {};
  } finally {
    creatingFolders.value = false;
  }
}

// one at a time, so a failed file is reported by name and the rest still upload
async function uploadAll() {
  const ready = queue.value.filter((q) => q.state === "ready");
  if (!ready.length || uploading.value) return;
  uploading.value = true;
  doneCount.value = 0;
  pending.value = ready.length;
  const folders = await makeFolders(ready);
  const madeFolders = Object.keys(folders).length > 0;
  const added: string[] = [];
  for (const item of ready) {
    if (item.state !== "ready") {
      doneCount.value++;
      continue;
    }
    item.state = "uploading";
    try {
      const saved = await new FileUploadHandler().upload(item.file, {
        upload_endpoint: uploadUrl(
          item.dir ? folders[item.dir] : props.folder?.name ?? null
        ),
        private: true,
      });
      item.state = "done";
      added.push(saved.name);
    } catch (e: any) {
      item.state = "error";
      item.error = e?.message || __("Couldn't upload this file.");
    }
    doneCount.value++;
  }
  uploading.value = false;
  if (added.length || madeFolders) emit("uploaded");
  if (added.length) {
    toast.success(
      added.length === 1
        ? __("1 file added")
        : __("{0} files added", String(added.length))
    );
    if (props.folder || madeFolders) notifyFolderPeople(added);
  }
  // keep the dialog open while something failed, so the reason stays readable
  if (queue.value.every((q) => q.state === "done")) emit("update:open", false);
}

// one notification per person for the whole upload, not one per file
function notifyFolderPeople(files: string[]) {
  call("helpdesk.api.project_files.notify_folder_upload", {
    project: props.projectId,
    files,
  }).catch(() =>
    toast.error(
      __(
        "The files were added, but the people their folders are for weren't notified."
      )
    )
  );
}

function onOpenChange(value: boolean) {
  if (!value && uploading.value) return;
  emit("update:open", value);
}
</script>
