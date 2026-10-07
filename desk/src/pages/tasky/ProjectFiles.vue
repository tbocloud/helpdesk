<template>
  <div class="flex h-full flex-col">
    <ProjectNav ref="nav" :project-id="projectId">
      <template #actions>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="files.loading && !!files.data"
          @click="files.reload()"
        >
          <template #icon><LucideRefreshCw class="size-4" /></template>
        </Button>
      </template>
    </ProjectNav>

    <div
      class="relative flex-1 overflow-auto"
      @dragenter.prevent="onDragEnter"
      @dragover.prevent
      @dragleave="onDragLeave"
      @drop.prevent="onDrop"
    >
      <div
        v-if="dragging"
        class="pointer-events-none absolute inset-3 z-10 flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-brand bg-brand-soft"
        aria-hidden="true"
      >
        <LucideUpload class="size-6 text-brand-ink" />
        <span class="text-base-medium text-brand-ink">
          {{ __("Drop to add to this project") }}
        </span>
      </div>

      <div class="mx-auto w-full max-w-5xl px-4 py-5 md:px-6">
        <TaskyState
          v-if="files.error && !files.data"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the files')"
          :message="loadErrorMessage(files.error)"
        >
          <Button :label="__('Retry')" @click="files.reload()" />
        </TaskyState>

        <template v-else>
          <div class="mb-4 flex flex-wrap items-center gap-2">
            <h2 class="text-lg-semibold text-ink-gray-9">{{ __("Files") }}</h2>
            <span
              v-if="files.data"
              class="font-mono text-sm tabular-nums text-ink-gray-5"
            >
              {{ files.data.total }}
            </span>
            <div class="ml-auto flex items-center gap-2">
              <Button
                :aria-pressed="forMe"
                :label="__('For me')"
                :class="forMe ? 'ring-2 ring-inset ring-brand' : ''"
                @click="forMe = !forMe"
              >
                <template #prefix>
                  <LucideUserCheck class="size-4" aria-hidden="true" />
                </template>
              </Button>
              <Button
                v-if="files.data?.can_upload"
                :label="__('Add files')"
                @click="openUpload([])"
              >
                <template #prefix>
                  <LucidePaperclip class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </div>
          </div>

          <!-- Loading -->
          <div
            v-if="!files.data"
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            aria-busy="true"
          >
            <div
              v-for="i in 3"
              :key="i"
              class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
            >
              <div class="size-8 animate-pulse rounded-md bg-surface-gray-2" />
              <div class="flex flex-1 flex-col gap-2">
                <div
                  class="h-3.5 w-2/5 animate-pulse rounded bg-surface-gray-2"
                />
                <div
                  class="h-3 w-1/4 animate-pulse rounded bg-surface-gray-2"
                />
              </div>
            </div>
          </div>

          <TaskyState
            v-else-if="!files.data.files.length"
            :icon="forMe ? LucideUserCheck : LucidePaperclip"
            :title="
              forMe ? __('Nothing is marked for you') : __('No files yet')
            "
            :message="
              forMe
                ? __('Files someone marks as for you show up here.')
                : files.data.can_upload
                ? __(
                    'Add prompts, briefs, PDFs or designs. Everyone on the project can open them. Drop files anywhere on this page.'
                  )
                : __('Files added to this project show up here.')
            "
          >
            <Button
              v-if="forMe"
              :label="__('Show all files')"
              @click="forMe = false"
            />
            <Button
              v-else-if="files.data.can_upload"
              variant="solid"
              :label="__('Add files')"
              @click="openUpload([])"
            >
              <template #prefix>
                <LucidePaperclip class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </TaskyState>

          <ul
            v-else
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            role="list"
          >
            <li
              v-for="file in files.data.files"
              :key="file.name"
              class="flex flex-wrap items-start gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0 sm:flex-nowrap"
              :class="file.is_for_me ? 'bg-surface-gray-1' : ''"
            >
              <div
                class="grid size-8 shrink-0 place-items-center rounded-md bg-surface-gray-2 text-ink-gray-6"
              >
                <component
                  :is="fileIcon(file.file_name)"
                  class="size-4"
                  aria-hidden="true"
                />
              </div>

              <div class="flex min-w-0 flex-1 flex-col gap-1">
                <div class="flex min-w-0 flex-wrap items-center gap-2">
                  <button
                    v-if="canPreview(file.file_name)"
                    type="button"
                    class="min-w-0 truncate rounded text-left text-base-medium text-ink-gray-9 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                    @click="viewing = file"
                  >
                    {{ file.file_name }}
                  </button>
                  <a
                    v-else
                    :href="downloadHref(file.file_url)"
                    :download="file.file_name"
                    class="min-w-0 truncate rounded text-base-medium text-ink-gray-9 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                  >
                    {{ file.file_name }}
                  </a>
                  <span
                    v-if="file.is_for_me"
                    class="inline-flex shrink-0 items-center gap-1 rounded bg-info-soft px-1.5 py-0.5 text-xs font-medium text-info"
                  >
                    <LucideUserCheck class="size-3" aria-hidden="true" />
                    {{ __("For you") }}
                  </span>
                </div>
                <div
                  class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-gray-6"
                >
                  <span class="font-mono tabular-nums">{{
                    formatBytes(file.file_size)
                  }}</span>
                  <span aria-hidden="true">·</span>
                  <span>{{ file.uploaded_by_name }}</span>
                  <span aria-hidden="true">·</span>
                  <time
                    :datetime="file.creation"
                    :title="dateFormat(file.creation, dateTooltipFormat)"
                    >{{ timeAgo(file.creation) }}</time
                  >
                </div>
                <div
                  v-if="file.for_users.length"
                  class="flex flex-wrap items-center gap-1 pt-0.5"
                >
                  <span class="text-xs text-ink-gray-5">{{ __("For:") }}</span>
                  <span
                    v-for="person in file.for_users"
                    :key="person.user"
                    class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7"
                  >
                    {{ person.full_name }}
                  </span>
                </div>
              </div>

              <div class="flex shrink-0 items-center gap-0.5">
                <Button
                  v-if="canPreview(file.file_name)"
                  variant="ghost"
                  :tooltip="__('View')"
                  :aria-label="__('View {0}', file.file_name)"
                  @click="viewing = file"
                >
                  <template #icon>
                    <LucideEye class="size-4" aria-hidden="true" />
                  </template>
                </Button>
                <a
                  :href="downloadHref(file.file_url)"
                  :download="file.file_name"
                  class="grid size-7 place-items-center rounded text-ink-gray-7 transition-colors hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                  :aria-label="__('Download {0}', file.file_name)"
                  :title="__('Download')"
                >
                  <LucideDownload class="size-4" aria-hidden="true" />
                </a>
                <Button
                  v-if="file.can_edit_for"
                  variant="ghost"
                  :tooltip="__('Change who it\'s for')"
                  :aria-label="__('Change who {0} is for', file.file_name)"
                  @click="startEditFor(file)"
                >
                  <template #icon>
                    <LucideUsers class="size-4" aria-hidden="true" />
                  </template>
                </Button>
                <Button
                  v-if="file.can_delete"
                  variant="ghost"
                  :tooltip="__('Delete')"
                  :aria-label="__('Delete {0}', file.file_name)"
                  @click="deleting = file"
                >
                  <template #icon>
                    <LucideTrash2 class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </div>
            </li>
          </ul>
        </template>
      </div>
    </div>

    <UploadProjectFilesDialog
      v-if="files.data?.can_upload"
      v-model:open="showUpload"
      :project-id="projectId"
      :team="files.data.team"
      :max-file-size="files.data.max_file_size"
      :initial-files="droppedFiles"
      @uploaded="refresh"
    />

    <ProjectFileViewer v-model:file="viewing" :project-id="projectId" />

    <!-- who the file is for -->
    <Dialog
      :open="!!editingFor"
      :title="__('Who is it for?')"
      :message="editingFor?.file_name"
      size="lg"
      @update:open="(v: boolean) => !v && (editingFor = null)"
    >
      <FileForPicker v-model="forDraft" :team="files.data?.team ?? []" />
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="editingFor = null" />
          <Button
            variant="solid"
            :label="__('Save')"
            :loading="saveFor.loading"
            @click="
              saveFor.submit({
                project: projectId,
                file: editingFor?.name,
                for_users: forDraft,
              })
            "
          />
        </div>
      </template>
    </Dialog>

    <Dialog
      :open="!!deleting"
      :title="__('Delete file?')"
      :message="
        __(
          '{0} will be removed from the project for everyone. This can\'t be undone.',
          deleting?.file_name || ''
        )
      "
      size="md"
      @update:open="(v: boolean) => !v && (deleting = null)"
    >
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="deleting = null" />
          <Button
            variant="solid"
            theme="red"
            :label="__('Delete')"
            :loading="remove.loading"
            @click="remove.submit({ project: projectId, file: deleting?.name })"
          >
            <template #prefix>
              <LucideTrash2 class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { dateFormat, dateTooltipFormat, timeAgo } from "@/utils";
import { Button, Dialog, createResource, toast } from "frappe-ui";
import { ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideDownload from "~icons/lucide/download";
import LucideEye from "~icons/lucide/eye";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideTrash2 from "~icons/lucide/trash-2";
import LucideUpload from "~icons/lucide/upload";
import LucideUserCheck from "~icons/lucide/user-check";
import LucideUsers from "~icons/lucide/users";
import FileForPicker from "./components/FileForPicker.vue";
import ProjectFileViewer from "./components/ProjectFileViewer.vue";
import ProjectNav from "./components/ProjectNav.vue";
import TaskyState from "./components/TaskyState.vue";
import UploadProjectFilesDialog from "./components/UploadProjectFilesDialog.vue";
import {
  canPreview,
  downloadHref,
  fileIcon,
  formatBytes,
  type ProjectFile,
} from "./projectFiles";
import { errorText, loadErrorMessage } from "./taskMeta";

const props = defineProps<{ projectId: string }>();

const nav = ref<InstanceType<typeof ProjectNav> | null>(null);
const forMe = ref(false);
const viewing = ref<ProjectFile | null>(null);
const deleting = ref<ProjectFile | null>(null);
const editingFor = ref<ProjectFile | null>(null);
const forDraft = ref<string[]>([]);
const showUpload = ref(false);
const droppedFiles = ref<File[]>([]);
const dragging = ref(false);
let dragDepth = 0;

const files = createResource({
  url: "helpdesk.api.project_files.list_project_files",
  makeParams: () => ({ project: props.projectId, for_me: forMe.value }),
  auto: true,
  onError() {},
});

watch([() => props.projectId, forMe], () => files.reload());

/** Reload the file list and the project nav's file count badge. */
function refresh() {
  files.reload();
  nav.value?.reload();
}

/** Open the upload dialog, optionally pre-filled with files dropped on the page. */
function openUpload(dropped: File[]) {
  droppedFiles.value = dropped;
  showUpload.value = true;
}

/** dragenter/leave fire for every child element, so count the nesting. */
function onDragEnter(e: DragEvent) {
  if (!files.data?.can_upload || showUpload.value) return;
  if (!e.dataTransfer?.types.includes("Files")) return;
  dragDepth++;
  dragging.value = true;
}

/** Only hide the drop overlay once every nested dragleave has fired. */
function onDragLeave() {
  dragDepth = Math.max(dragDepth - 1, 0);
  if (!dragDepth) dragging.value = false;
}

/** Open the upload dialog with the files dropped on the page. */
function onDrop(e: DragEvent) {
  dragDepth = 0;
  dragging.value = false;
  if (!files.data?.can_upload || showUpload.value) return;
  const dropped = [...(e.dataTransfer?.files ?? [])];
  if (dropped.length) openUpload(dropped);
}

/** Open the "who is it for" dialog, pre-filled with the file's current assignees. */
function startEditFor(file: ProjectFile) {
  forDraft.value = file.for_users.map((p) => p.user);
  saveFor.reset();
  editingFor.value = file;
}

const saveFor = createResource({
  url: "helpdesk.api.project_files.set_project_file_for",
  onSuccess() {
    toast.success(__("Saved"));
    editingFor.value = null;
    files.reload();
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't save who it's for.")));
  },
});

const remove = createResource({
  url: "helpdesk.api.project_files.delete_project_file",
  onSuccess() {
    toast.success(__("File deleted"));
    deleting.value = null;
    refresh();
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't delete the file.")));
  },
});
</script>
