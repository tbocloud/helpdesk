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
      @dragover="onPageDragOver"
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
          {{
            currentFolder
              ? __("Drop to add to {0}", currentFolder.folder_name)
              : __("Drop to add to this project")
          }}
        </span>
      </div>

      <div class="mx-auto w-full max-w-5xl px-4 py-5 md:px-6">
        <p class="sr-only" aria-live="polite">{{ announcement }}</p>
        <TaskyState
          v-if="files.error && (!files.data || stale)"
          error
          :icon="LucideCircleAlert"
          :title="
            folderId
              ? __('Couldn\'t open this folder')
              : __('Couldn\'t load the files')
          "
          :message="loadErrorMessage(files.error)"
        >
          <Button :label="__('Retry')" @click="files.reload()" />
          <Button
            v-if="folderId"
            :label="__('Back to all files')"
            @click="openFolder(null)"
          />
        </TaskyState>

        <template v-else>
          <div class="mb-4 flex flex-wrap items-center gap-2">
            <nav
              v-if="folderId && !forMe"
              :aria-label="__('Breadcrumb')"
              class="min-w-0"
            >
              <ol class="flex min-w-0 items-center gap-1.5">
                <li
                  class="shrink-0 rounded px-1"
                  :class="dropClass('')"
                  v-on="dropHandlers('')"
                >
                  <RouterLink
                    :to="folderRoute(null)"
                    class="rounded text-lg-semibold text-ink-gray-5 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                  >
                    {{ __("Files") }}
                  </RouterLink>
                </li>
                <template v-for="crumb in ancestors" :key="crumb.name">
                  <li class="shrink-0 text-ink-gray-4" aria-hidden="true">/</li>
                  <li
                    class="min-w-0 max-w-40 truncate rounded px-1"
                    :class="dropClass(crumb.name)"
                    v-on="dropHandlers(crumb.name)"
                  >
                    <RouterLink
                      :to="folderRoute(crumb.name)"
                      class="rounded text-lg-semibold text-ink-gray-5 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                    >
                      {{ crumb.folder_name }}
                    </RouterLink>
                  </li>
                </template>
                <li class="shrink-0 text-ink-gray-4" aria-hidden="true">/</li>
                <li class="min-w-0" aria-current="page">
                  <h2 class="truncate text-lg-semibold text-ink-gray-9">
                    {{ currentFolder?.folder_name ?? "" }}
                  </h2>
                </li>
              </ol>
            </nav>
            <h2 v-else class="text-lg-semibold text-ink-gray-9">
              {{ __("Files") }}
            </h2>
            <span
              v-if="files.data && !stale"
              class="font-mono text-sm tabular-nums text-ink-gray-5"
            >
              {{ currentFolder ? files.data.files.length : files.data.total }}
            </span>
            <div class="ml-auto flex flex-wrap items-center gap-2">
              <Button
                :aria-pressed="forMe"
                :label="__('For me')"
                :class="forMe ? 'ring-2 ring-inset ring-brand' : ''"
                @click="toggleForMe"
              >
                <template #prefix>
                  <LucideUserCheck class="size-4" aria-hidden="true" />
                </template>
              </Button>
              <Dropdown
                v-if="currentFolder"
                :options="folderMenu(currentFolder, false)"
                align="end"
              >
                <Button
                  :label="__('Folder')"
                  :aria-label="
                    __('Actions for folder {0}', currentFolder.folder_name)
                  "
                >
                  <template #prefix>
                    <LucideFolderCog class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </Dropdown>
              <Button
                v-if="canAddFolderHere"
                :label="__('New folder')"
                @click="startCreateFolder"
              >
                <template #prefix>
                  <LucideFolderPlus class="size-4" aria-hidden="true" />
                </template>
              </Button>
              <Button
                v-if="canUpload && !forMe"
                :label="__('Add files')"
                @click="openUpload([])"
              >
                <template #prefix>
                  <LucidePaperclip class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </div>
          </div>

          <!-- the open folder: what it's for and who it's for -->
          <div
            v-if="currentFolder && !stale"
            class="-mt-2 mb-4 flex flex-col gap-1.5"
          >
            <div
              v-if="supersededVia(currentFolder)"
              class="flex flex-wrap items-center gap-2"
            >
              <TaskyBadge
                :icon="LucideArchive"
                :label="
                  supersededVia(currentFolder) === 'own'
                    ? __('Superseded')
                    : __('In a superseded folder')
                "
              />
              <span class="text-p-sm text-ink-gray-6">
                {{ __("Everything here is an older version.") }}
              </span>
              <SupersededNote
                :item="currentFolder"
                :to="replacementRoute(currentFolder)"
              />
            </div>
            <p
              v-if="currentFolder.description"
              class="text-p-sm text-ink-gray-6"
            >
              {{ currentFolder.description }}
            </p>
            <PeopleChips :people="currentFolder.for_users" />
          </div>

          <!-- superseded versions are hidden by default, so the current set is clear -->
          <p
            v-if="files.data && !stale && (hiddenCount || showSuperseded)"
            class="mb-3 flex flex-wrap items-center gap-x-1.5 text-xs text-ink-gray-6"
          >
            <LucideArchive class="size-3.5" aria-hidden="true" />
            <span v-if="showSuperseded">
              {{ __("Showing superseded files and folders") }}
            </span>
            <span v-else class="tabular-nums">
              {{
                hiddenCount === 1
                  ? __("1 superseded hidden")
                  : __("{0} superseded hidden", String(hiddenCount))
              }}
            </span>
            <span aria-hidden="true">·</span>
            <button
              type="button"
              class="rounded font-medium text-ink-gray-8 underline decoration-outline-gray-3 underline-offset-2 hover:decoration-ink-gray-6 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              @click="setShowSuperseded(!showSuperseded)"
            >
              {{ showSuperseded ? __("Hide superseded") : __("Show") }}
            </button>
          </p>

          <!-- Loading -->
          <div
            v-if="!files.data || stale"
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

          <template v-else>
            <!-- the folders in this one (or at the top level) -->
            <ul
              v-if="!forMe && subfolders.length"
              class="mb-4 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
              role="list"
              :aria-label="__('Folders')"
            >
              <li
                v-for="folder in subfolders"
                :key="folder.name"
                class="flex items-start gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
                :class="[
                  folder.is_for_me || folder.for_me_via_parent
                    ? 'bg-surface-gray-1'
                    : '',
                  folder.can_change ? 'cursor-grab' : '',
                  dropClass(folder.name),
                ]"
                :draggable="folder.can_change"
                :aria-busy="movingTo === folder.name"
                @dragstart="onItemDragStart($event, folderMoveItem(folder))"
                @dragend="onItemDragEnd"
                v-on="dropHandlers(folder.name)"
              >
                <div
                  class="grid size-8 shrink-0 place-items-center rounded-md bg-surface-gray-2 text-ink-gray-6"
                >
                  <LucideLoaderCircle
                    v-if="movingTo === folder.name"
                    class="size-4 animate-spin"
                    aria-hidden="true"
                  />
                  <LucideFolder v-else class="size-4" aria-hidden="true" />
                </div>
                <div class="flex min-w-0 flex-1 flex-col gap-1">
                  <div class="flex min-w-0 flex-wrap items-center gap-2">
                    <RouterLink
                      :to="folderRoute(folder.name)"
                      class="min-w-0 truncate rounded text-base-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                      :class="
                        supersededVia(folder)
                          ? 'text-ink-gray-6'
                          : 'text-ink-gray-9'
                      "
                    >
                      {{ folder.folder_name }}
                    </RouterLink>
                    <TaskyBadge
                      v-if="supersededVia(folder)"
                      :icon="LucideArchive"
                      :label="
                        supersededVia(folder) === 'own'
                          ? __('Superseded')
                          : __('In a superseded folder')
                      "
                    />
                    <TaskyBadge
                      v-if="folder.is_for_me"
                      tone="info"
                      :icon="LucideUserCheck"
                      :label="__('For you')"
                    />
                    <TaskyBadge
                      v-else-if="folder.for_me_via_parent"
                      tone="info"
                      :icon="LucideFolder"
                      :label="__('In a folder for you')"
                    />
                  </div>
                  <SupersededNote
                    :item="folder"
                    :to="replacementRoute(folder)"
                  />
                  <div
                    class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-gray-6"
                  >
                    <span class="font-mono tabular-nums">{{
                      folderCounts(folder)
                    }}</span>
                    <span aria-hidden="true">·</span>
                    <span>{{ folder.created_by_name }}</span>
                    <template v-if="folder.description">
                      <span aria-hidden="true">·</span>
                      <span
                        class="min-w-0 max-w-full truncate"
                        :title="folder.description"
                        >{{ folder.description }}</span
                      >
                    </template>
                  </div>
                  <PeopleChips :people="folder.for_users" />
                </div>
                <Button
                  v-if="folder.comment_count"
                  variant="ghost"
                  class="min-h-11 md:min-h-0"
                  :aria-label="
                    commentsLabel(folder.comment_count, folder.folder_name)
                  "
                  @click="commenting = folderRef(folder)"
                >
                  <template #prefix>
                    <LucideMessageSquare class="size-4" aria-hidden="true" />
                  </template>
                  <span class="font-mono tabular-nums">{{
                    folder.comment_count
                  }}</span>
                </Button>
                <Dropdown :options="folderMenu(folder, true)" align="end">
                  <Button
                    variant="ghost"
                    class="min-h-11 min-w-11 md:min-h-0 md:min-w-0"
                    :aria-label="
                      __('Actions for folder {0}', folder.folder_name)
                    "
                  >
                    <template #icon>
                      <LucideEllipsis class="size-4" aria-hidden="true" />
                    </template>
                  </Button>
                </Dropdown>
              </li>
            </ul>

            <TaskyState
              v-if="
                hiddenCount &&
                !files.data.files.length &&
                (forMe || !subfolders.length)
              "
              :icon="LucideArchive"
              :title="__('Only superseded versions here')"
              :message="
                __(
                  'Older versions are hidden so the current ones stand out. Show them to see what was replaced.'
                )
              "
            >
              <Button
                :label="__('Show superseded')"
                @click="setShowSuperseded(true)"
              />
            </TaskyState>

            <TaskyState
              v-else-if="forMe && !files.data.files.length"
              :icon="LucideUserCheck"
              :title="__('Nothing is marked for you')"
              :message="
                __(
                  'Files someone marks as for you, and files in folders shared with you, show up here.'
                )
              "
            >
              <Button :label="__('Show all files')" @click="forMe = false" />
            </TaskyState>

            <TaskyState
              v-else-if="
                currentFolder && !files.data.files.length && !subfolders.length
              "
              :icon="LucideFolderOpen"
              :title="__('This folder is empty')"
              :message="
                canUpload
                  ? __(
                      'Add files or a whole folder here, or drop them anywhere on this page. Files already on the project move in from their menu.'
                    )
                  : __('Files added to this folder show up here.')
              "
            >
              <Button
                v-if="canUpload"
                variant="solid"
                :label="__('Add files')"
                @click="openUpload([])"
              >
                <template #prefix>
                  <LucidePaperclip class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </TaskyState>

            <TaskyState
              v-else-if="
                !currentFolder && !files.data.files.length && !subfolders.length
              "
              :icon="LucidePaperclip"
              :title="__('No files yet')"
              :message="
                canUpload
                  ? __(
                      'Add prompts, briefs, PDFs or designs. Everyone on the project can open them. Drop files anywhere on this page.'
                    )
                  : __('Files added to this project show up here.')
              "
            >
              <Button
                v-if="canUpload"
                variant="solid"
                :label="__('Add files')"
                @click="openUpload([])"
              >
                <template #prefix>
                  <LucidePaperclip class="size-4" aria-hidden="true" />
                </template>
              </Button>
              <Button
                v-if="canUpload"
                :label="__('New folder')"
                @click="startCreateFolder"
              >
                <template #prefix>
                  <LucideFolderPlus class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </TaskyState>

            <ul
              v-else-if="files.data.files.length"
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
              role="list"
              :aria-label="__('Files')"
            >
              <li
                v-for="file in files.data.files"
                :key="file.name"
                class="flex flex-wrap items-start gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0 sm:flex-nowrap"
                :class="[
                  file.is_for_me || file.shared_via_folder
                    ? 'bg-surface-gray-1'
                    : '',
                  canDrag(file) ? 'cursor-grab' : '',
                  dragItem?.name === file.name ? 'opacity-50' : '',
                ]"
                :draggable="canDrag(file)"
                @dragstart="onItemDragStart($event, fileMoveItem(file))"
                @dragend="onItemDragEnd"
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
                      class="min-w-0 truncate rounded text-left text-base-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                      :class="
                        supersededVia(file)
                          ? 'text-ink-gray-6'
                          : 'text-ink-gray-9'
                      "
                      @click="viewing = file"
                    >
                      {{ file.file_name }}
                    </button>
                    <a
                      v-else
                      :href="downloadHref(file.file_url)"
                      :download="file.file_name"
                      class="min-w-0 truncate rounded text-base-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                      :class="
                        supersededVia(file)
                          ? 'text-ink-gray-6'
                          : 'text-ink-gray-9'
                      "
                    >
                      {{ file.file_name }}
                    </a>
                    <TaskyBadge
                      v-if="supersededVia(file)"
                      :icon="LucideArchive"
                      :label="
                        supersededVia(file) === 'own'
                          ? __('Superseded')
                          : __('In a superseded folder')
                      "
                    />
                    <TaskyBadge
                      v-if="file.is_for_me"
                      tone="info"
                      :icon="LucideUserCheck"
                      :label="__('For you')"
                    />
                    <TaskyBadge
                      v-else-if="file.shared_via_folder"
                      tone="info"
                      :icon="LucideFolder"
                      :label="__('In a folder for you')"
                    />
                  </div>
                  <div
                    class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-gray-6"
                  >
                    <template v-if="forMe && file.folder">
                      <RouterLink
                        :to="folderRoute(file.folder)"
                        class="inline-flex min-w-0 items-center gap-1 rounded hover:text-ink-gray-8 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                      >
                        <LucideFolder
                          class="size-3 shrink-0"
                          aria-hidden="true"
                        />
                        <span class="truncate">{{
                          file.folder_path.map((p) => p.folder_name).join(" / ")
                        }}</span>
                      </RouterLink>
                      <span aria-hidden="true">·</span>
                    </template>
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
                  <SupersededNote :item="file" :to="replacementRoute(file)" />
                  <PeopleChips :people="file.for_users" />
                </div>

                <div class="flex shrink-0 items-center gap-0.5">
                  <Button
                    v-if="file.comment_count"
                    variant="ghost"
                    class="min-h-11 md:min-h-0"
                    :aria-label="
                      commentsLabel(file.comment_count, file.file_name)
                    "
                    @click="commenting = fileRef(file)"
                  >
                    <template #prefix>
                      <LucideMessageSquare class="size-4" aria-hidden="true" />
                    </template>
                    <span class="font-mono tabular-nums">{{
                      file.comment_count
                    }}</span>
                  </Button>
                  <Button
                    v-if="canPreview(file.file_name)"
                    variant="ghost"
                    class="min-h-11 min-w-11 md:min-h-0 md:min-w-0"
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
                    class="grid size-11 place-items-center rounded text-ink-gray-7 transition-colors hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4 md:size-7"
                    :aria-label="__('Download {0}', file.file_name)"
                    :title="__('Download')"
                  >
                    <LucideDownload class="size-4" aria-hidden="true" />
                  </a>
                  <Dropdown :options="fileMenu(file)" align="end">
                    <Button
                      variant="ghost"
                      class="min-h-11 min-w-11 md:min-h-0 md:min-w-0"
                      :aria-label="__('More actions for {0}', file.file_name)"
                    >
                      <template #icon>
                        <LucideEllipsis class="size-4" aria-hidden="true" />
                      </template>
                    </Button>
                  </Dropdown>
                </div>
              </li>
            </ul>
          </template>
        </template>
      </div>
    </div>

    <UploadProjectFilesDialog
      v-if="canUpload"
      v-model:open="showUpload"
      :project-id="projectId"
      :team="files.data?.team ?? []"
      :max-file-size="files.data?.max_file_size ?? 0"
      :max-upload-files="files.data?.max_upload_files ?? 200"
      :initial-files="droppedFiles"
      :folder="currentFolder"
      @uploaded="refresh"
    />

    <ProjectFileViewer v-model:file="viewing" :project-id="projectId" />

    <ProjectFolderDialog
      v-model:open="showFolderDialog"
      :project-id="projectId"
      :team="files.data?.team ?? []"
      :folder="renaming"
      :parent="currentFolder"
      @saved="onFolderSaved"
    />

    <MoveToFolderDialog
      v-model:item="moving"
      :project-id="projectId"
      :folders="files.data?.folders ?? []"
      :max-depth="maxDepth"
      @moved="files.reload()"
    />

    <SupersedeDialog
      v-model:item="superseding"
      :project-id="projectId"
      @saved="files.reload()"
    />

    <ItemCommentsDialog
      v-model:item="commenting"
      :project-id="projectId"
      @changed="files.reload()"
    />

    <!-- who a file or folder is for -->
    <Dialog
      :open="!!editingFor"
      :title="__('Who is it for?')"
      :message="editingFor?.label"
      size="lg"
      @update:open="(v: boolean) => !v && (editingFor = null)"
    >
      <FileForPicker
        v-model="forDraft"
        :team="files.data?.team ?? []"
        :folder="editingFor?.kind === 'folder'"
      />
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="editingFor = null" />
          <Button
            variant="solid"
            :label="__('Save')"
            :loading="saveFileFor.loading || saveFolderFor.loading"
            @click="submitFor"
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
            :label="__('Delete file')"
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

    <Dialog
      :open="!!deletingFolder"
      :title="__('Delete folder?')"
      :message="deleteFolderMessage"
      size="md"
      @update:open="(v: boolean) => !v && (deletingFolder = null)"
    >
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="deletingFolder = null" />
          <Button
            variant="solid"
            theme="red"
            :label="__('Delete folder')"
            :loading="removeFolder.loading"
            @click="
              removeFolder.submit({
                project: projectId,
                folder: deletingFolder?.name,
              })
            "
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
import { dateFormat, dateTooltipFormat, errorText, timeAgo } from "@/utils";
import {
  Button,
  Dialog,
  Dropdown,
  call,
  createResource,
  toast,
} from "frappe-ui";
import { computed, ref, watch, type Component } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import LucideArchive from "~icons/lucide/archive";
import LucideArchiveRestore from "~icons/lucide/archive-restore";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideDownload from "~icons/lucide/download";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideEye from "~icons/lucide/eye";
import LucideFolder from "~icons/lucide/folder";
import LucideFolderCog from "~icons/lucide/folder-cog";
import LucideFolderInput from "~icons/lucide/folder-input";
import LucideFolderOpen from "~icons/lucide/folder-open";
import LucideFolderPlus from "~icons/lucide/folder-plus";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucideMessageSquare from "~icons/lucide/message-square";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucidePencil from "~icons/lucide/pencil";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideTrash2 from "~icons/lucide/trash-2";
import LucideUpload from "~icons/lucide/upload";
import LucideUserCheck from "~icons/lucide/user-check";
import LucideUsers from "~icons/lucide/users";
import FileForPicker from "./components/FileForPicker.vue";
import ItemCommentsDialog from "./components/ItemCommentsDialog.vue";
import MoveToFolderDialog from "./components/MoveToFolderDialog.vue";
import PeopleChips from "./components/PeopleChips.vue";
import ProjectFileViewer from "./components/ProjectFileViewer.vue";
import ProjectFolderDialog from "./components/ProjectFolderDialog.vue";
import ProjectNav from "./components/ProjectNav.vue";
import SupersedeDialog from "./components/SupersedeDialog.vue";
import SupersededNote from "./components/SupersededNote.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import UploadProjectFilesDialog from "./components/UploadProjectFilesDialog.vue";
import {
  canPreview,
  downloadHref,
  fileIcon,
  formatBytes,
  fromDataTransfer,
  subtree,
  supersededVia,
  type ItemRef,
  type MoveItem,
  type OpenFolder,
  type ProjectFile,
  type ProjectFolder,
  type UploadItem,
} from "./projectFiles";
import { loadErrorMessage } from "./taskMeta";

interface ForTarget {
  kind: "file" | "folder";
  name: string;
  label: string;
}

const props = defineProps<{ projectId: string }>();

const route = useRoute();
const router = useRouter();
const nav = ref<InstanceType<typeof ProjectNav> | null>(null);
const forMe = ref(false);
const viewing = ref<ProjectFile | null>(null);
const deleting = ref<ProjectFile | null>(null);
const moving = ref<MoveItem | null>(null);
const editingFor = ref<ForTarget | null>(null);
const forDraft = ref<string[]>([]);
const showUpload = ref(false);
const droppedFiles = ref<UploadItem[]>([]);
const showFolderDialog = ref(false);
const renaming = ref<ProjectFolder | null>(null);
const deletingFolder = ref<ProjectFolder | null>(null);
const superseding = ref<ItemRef | null>(null);
const commenting = ref<ItemRef | null>(null);
const dragging = ref(false);
let dragDepth = 0;

// the open folder lives in the URL (?folder=), so it survives a reload and can be linked
const folderId = computed(() =>
  typeof route.query.folder === "string" ? route.query.folder : ""
);

// superseded files and folders are hidden unless ?superseded=1, so the current set is clear
const showSuperseded = computed(() => route.query.superseded === "1");

const files = createResource({
  url: "helpdesk.api.project_files.list_project_files",
  makeParams: () => ({
    project: props.projectId,
    folder: forMe.value ? null : folderId.value || null,
    for_me: forMe.value,
    show_superseded: showSuperseded.value,
  }),
  auto: true,
  onError() {},
});

watch([() => props.projectId, forMe, folderId, showSuperseded], () =>
  files.reload()
);

// the data on screen is for another folder while the new one loads
const stale = computed(
  () =>
    !forMe.value && (files.data?.folder?.name ?? "") !== (folderId.value || "")
);
const currentFolder = computed<OpenFolder | null>(() =>
  !forMe.value && !stale.value ? files.data?.folder ?? null : null
);
const ancestors = computed(() => currentFolder.value?.path.slice(0, -1) ?? []);
const canUpload = computed(() => !!files.data?.can_upload);
const maxDepth = computed<number>(() => files.data?.max_depth ?? 5);
const subfolders = computed<ProjectFolder[]>(() =>
  (files.data?.folders ?? []).filter(
    (f: ProjectFolder) =>
      (f.parent_folder ?? "") === folderId.value &&
      !(files.data.hiding_superseded && supersededVia(f))
  )
);
const hiddenCount = computed<number>(() =>
  stale.value ? 0 : files.data?.superseded_hidden ?? 0
);
const canAddFolderHere = computed(
  () =>
    canUpload.value &&
    !forMe.value &&
    !stale.value &&
    (currentFolder.value?.depth ?? 0) < maxDepth.value
);

function folderCounts(folder: ProjectFolder) {
  const parts = [
    folder.file_count === 1
      ? __("1 file")
      : __("{0} files", String(folder.file_count)),
  ];
  if (folder.folder_count)
    parts.push(
      folder.folder_count === 1
        ? __("1 folder")
        : __("{0} folders", String(folder.folder_count))
    );
  return parts.join(", ");
}

function folderRoute(folder: string | null) {
  const query = { ...route.query };
  if (folder) query.folder = folder;
  else delete query.folder;
  return { query };
}

function openFolder(folder: string | null) {
  router.push(folderRoute(folder));
}

function toggleForMe() {
  forMe.value = !forMe.value;
  if (forMe.value && folderId.value) router.replace(folderRoute(null));
}

function refresh() {
  files.reload();
  nav.value?.reload();
}

function openUpload(dropped: UploadItem[]) {
  droppedFiles.value = dropped;
  showUpload.value = true;
}

// dragenter/leave fire for every child element, so count the nesting
function onDragEnter(e: DragEvent) {
  if (!canUpload.value || forMe.value || showUpload.value) return;
  if (!e.dataTransfer?.types.includes("Files")) return;
  dragDepth++;
  dragging.value = true;
}

function onDragLeave() {
  dragDepth = Math.max(dragDepth - 1, 0);
  if (!dragDepth) dragging.value = false;
}

async function onDrop(e: DragEvent) {
  dragDepth = 0;
  dragging.value = false;
  if (!canUpload.value || forMe.value || showUpload.value) return;
  if (!e.dataTransfer) return;
  const dropped = await fromDataTransfer(e.dataTransfer);
  if (dropped.length) openUpload(dropped);
}

interface MenuItem {
  label: string;
  icon: Component;
  onClick: () => void;
  theme?: "red";
}

function folderMenu(folder: ProjectFolder, withOpen: boolean): MenuItem[] {
  const items: MenuItem[] = [];
  if (withOpen)
    items.push({
      label: __("Open"),
      icon: LucideFolderOpen,
      onClick: () => openFolder(folder.name),
    });
  items.push({
    label: __("Comments"),
    icon: LucideMessageSquare,
    onClick: () => (commenting.value = folderRef(folder)),
  });
  if (!folder.can_change) return items;
  items.push(
    statusMenuItem(folder, folderRef(folder)),
    {
      label: __("Rename"),
      icon: LucidePencil,
      onClick: () => {
        renaming.value = folder;
        showFolderDialog.value = true;
      },
    },
    {
      label: __("Move to folder…"),
      icon: LucideFolderInput,
      onClick: () => (moving.value = folderMoveItem(folder)),
    },
    {
      label: __("Change who it's for"),
      icon: LucideUsers,
      onClick: () =>
        startEditFor(
          { kind: "folder", name: folder.name, label: folder.folder_name },
          folder.for_users.map((p) => p.user)
        ),
    },
    {
      label: __("Delete folder"),
      icon: LucideTrash2,
      theme: "red",
      onClick: () => (deletingFolder.value = folder),
    }
  );
  return items;
}

function fileMenu(file: ProjectFile): MenuItem[] {
  const comments: MenuItem = {
    label: __("Comments"),
    icon: LucideMessageSquare,
    onClick: () => (commenting.value = fileRef(file)),
  };
  if (!file.can_edit_for) return [comments];
  const items: MenuItem[] = [
    comments,
    statusMenuItem(file, fileRef(file)),
    {
      label: __("Change who it's for"),
      icon: LucideUsers,
      onClick: () =>
        startEditFor(
          { kind: "file", name: file.name, label: file.file_name },
          file.for_users.map((p) => p.user)
        ),
    },
  ];
  if (files.data?.folders.length || file.folder)
    items.push({
      label: __("Move to folder…"),
      icon: LucideFolderInput,
      onClick: () => (moving.value = fileMoveItem(file)),
    });
  if (file.can_delete)
    items.push({
      label: __("Delete file"),
      icon: LucideTrash2,
      theme: "red",
      onClick: () => (deleting.value = file),
    });
  return items;
}

function commentsLabel(count: number, label: string) {
  return count === 1
    ? __("1 comment on {0}", label)
    : __("{0} comments on {1}", String(count), label);
}

function fileRef(file: ProjectFile): ItemRef {
  return { kind: "file", name: file.name, label: file.file_name };
}

function folderRef(folder: ProjectFolder): ItemRef {
  return { kind: "folder", name: folder.name, label: folder.folder_name };
}

// --- Active / Superseded, the same for files and folders ---

function statusMenuItem(
  item: ProjectFile | ProjectFolder,
  target: ItemRef
): MenuItem {
  return item.status === "Superseded"
    ? {
        label: __("Mark as active"),
        icon: LucideArchiveRestore,
        onClick: () => markActive(target),
      }
    : {
        label: __("Mark as superseded…"),
        icon: LucideArchive,
        onClick: () => (superseding.value = target),
      };
}

async function markActive(item: ItemRef) {
  try {
    await call("helpdesk.api.project_files.set_project_item_status", {
      project: props.projectId,
      kind: item.kind,
      item: item.name,
      status: "Active",
    });
    toast.success(__("{0} is active again", item.label));
    files.reload();
  } catch (e) {
    toast.error(errorText(e, __("Couldn't mark {0} as active.", item.label)));
  }
}

function setShowSuperseded(show: boolean) {
  const query = { ...route.query };
  if (show) query.superseded = "1";
  else delete query.superseded;
  router.replace({ query });
}

/** Where the replacement of a superseded file or folder is. */
function replacementRoute(item: ProjectFile | ProjectFolder) {
  const target = item.superseded_by;
  if (!target) return folderRoute(null);
  return folderRoute(
    "folder_name" in item ? target.name : target.folder ?? null
  );
}

// a notification about a comment links here with ?comments=<file or folder>
watch(
  () => [files.data, route.query.comments] as const,
  ([data, wanted]) => {
    if (!data || typeof wanted !== "string" || stale.value) return;
    const file = data.files.find((f: ProjectFile) => f.name === wanted);
    const folder = data.folders.find((f: ProjectFolder) => f.name === wanted);
    if (file || folder)
      commenting.value = file ? fileRef(file) : folderRef(folder!);
    const query = { ...route.query };
    delete query.comments;
    router.replace({ query });
  },
  { immediate: true }
);

function fileMoveItem(file: ProjectFile): MoveItem {
  return {
    kind: "file",
    name: file.name,
    label: file.file_name,
    current: file.folder,
  };
}

function folderMoveItem(folder: ProjectFolder): MoveItem {
  return {
    kind: "folder",
    name: folder.name,
    label: folder.folder_name,
    current: folder.parent_folder,
    height: folder.height,
  };
}

// --- moving by drag and drop; "Move to folder…" in each menu does the same by keyboard ---

// in-app drags carry this type; drags from the computer carry "Files" (uploads)
const ITEM_MIME = "application/x-tbo-project-item";
const dragItem = ref<MoveItem | null>(null);
// "" is the top level
const dropTarget = ref<string | null>(null);
const movingTo = ref<string | null>(null);
const announcement = ref("");

function canDrag(file: ProjectFile) {
  return file.can_edit_for && !forMe.value;
}

function onItemDragStart(e: DragEvent, item: MoveItem) {
  if (!e.dataTransfer) return;
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData(ITEM_MIME, item.name);
  dragItem.value = item;
}

function onItemDragEnd() {
  dragItem.value = null;
  dropTarget.value = null;
}

function canDropOn(target: string) {
  const item = dragItem.value;
  if (!item || movingTo.value !== null) return false;
  if ((item.current ?? "") === target || item.name === target) return false;
  if (item.kind === "file") return true;
  const folders: ProjectFolder[] = files.data?.folders ?? [];
  if (target && subtree(folders, item.name).has(target)) return false;
  const depth = folders.find((f) => f.name === target)?.depth ?? 0;
  return depth + (item.height ?? 1) <= maxDepth.value;
}

function dropClass(target: string) {
  if (movingTo.value === target || dropTarget.value === target)
    return "ring-2 ring-inset ring-outline-gray-6";
  // a folder can't go into itself, below itself, or too deep
  const item = dragItem.value;
  if (
    item?.kind === "folder" &&
    (item.current ?? "") !== target &&
    !canDropOn(target)
  )
    return "opacity-50";
  return "";
}

function isItemDrag(e: DragEvent) {
  return !!e.dataTransfer?.types.includes(ITEM_MIME);
}

function dropHandlers(target: string) {
  return {
    dragover(e: DragEvent) {
      if (!isItemDrag(e) || !canDropOn(target)) return;
      e.preventDefault();
      e.stopPropagation();
      e.dataTransfer!.dropEffect = "move";
      dropTarget.value = target;
    },
    dragleave() {
      if (dropTarget.value === target) dropTarget.value = null;
    },
    drop(e: DragEvent) {
      if (!isItemDrag(e)) return;
      e.preventDefault();
      e.stopPropagation();
      const item = dragItem.value;
      const valid = canDropOn(target);
      onItemDragEnd();
      if (item && valid) moveByDrop(item, target);
    },
  };
}

// only uploads from the computer may drop on the page itself
function onPageDragOver(e: DragEvent) {
  if (e.dataTransfer?.types.includes("Files")) e.preventDefault();
}

async function moveByDrop(item: MoveItem, target: string) {
  movingTo.value = target;
  const where = target
    ? files.data?.folders.find((f: ProjectFolder) => f.name === target)
        ?.folder_name ?? ""
    : __("Files");
  try {
    if (item.kind === "folder")
      await call("helpdesk.api.project_files.move_project_folder", {
        project: props.projectId,
        folder: item.name,
        parent_folder: target || null,
      });
    else
      await call("helpdesk.api.project_files.move_project_file", {
        project: props.projectId,
        file: item.name,
        folder: target || null,
      });
    const message = __("Moved {0} to {1}", item.label, where);
    announcement.value = message;
    toast.success(message);
    await files.reload();
  } catch (e) {
    const message = errorText(e, __("Couldn't move {0}.", item.label));
    announcement.value = message;
    toast.error(message);
  } finally {
    movingTo.value = null;
  }
}

function startCreateFolder() {
  renaming.value = null;
  showFolderDialog.value = true;
}

function onFolderSaved(folder: { name: string; folder_name: string }) {
  if (renaming.value) {
    toast.success(__("Folder renamed"));
    files.reload();
    return;
  }
  toast.success(__("Folder {0} created", folder.folder_name));
  openFolder(folder.name);
}

function startEditFor(target: ForTarget, users: string[]) {
  forDraft.value = users;
  saveFileFor.reset();
  saveFolderFor.reset();
  editingFor.value = target;
}

function submitFor() {
  const target = editingFor.value;
  if (!target) return;
  if (target.kind === "folder")
    saveFolderFor.submit({
      project: props.projectId,
      folder: target.name,
      for_users: forDraft.value,
    });
  else
    saveFileFor.submit({
      project: props.projectId,
      file: target.name,
      for_users: forDraft.value,
    });
}

const forHandlers = {
  onSuccess() {
    toast.success(__("Saved"));
    editingFor.value = null;
    files.reload();
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't save who it's for.")));
  },
};
const saveFileFor = createResource({
  url: "helpdesk.api.project_files.set_project_file_for",
  ...forHandlers,
});
const saveFolderFor = createResource({
  url: "helpdesk.api.project_files.set_project_folder_for",
  ...forHandlers,
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

const deleteFolderMessage = computed(() => {
  const folder = deletingFolder.value;
  if (!folder) return "";
  if (!folder.file_count && !folder.folder_count)
    return __(
      "{0} is empty. It will be removed for everyone.",
      folder.folder_name
    );
  const parent = files.data?.folders.find(
    (f: ProjectFolder) => f.name === folder.parent_folder
  );
  return __(
    "{0} will be removed for everyone. What's in it ({1}) moves up to {2}; nothing is deleted.",
    folder.folder_name,
    folderCounts(folder),
    parent ? parent.folder_name : __("the top of Files")
  );
});

const removeFolder = createResource({
  url: "helpdesk.api.project_files.delete_project_folder",
  onSuccess() {
    toast.success(__("Folder deleted"));
    const gone = deletingFolder.value;
    deletingFolder.value = null;
    // the open folder is gone: show where its contents went
    if (gone?.name === folderId.value) openFolder(gone.parent_folder);
    else files.reload();
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't delete the folder.")));
  },
});
</script>
