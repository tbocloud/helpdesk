<template>
  <section
    :aria-labelledby="headingId"
    class="relative flex flex-col gap-2 rounded-lg"
    :class="dragging ? 'ring-2 ring-brand ring-offset-4' : ''"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
  >
    <div class="flex items-center justify-between gap-2">
      <h3
        :id="headingId"
        class="flex items-center gap-2 text-xs text-ink-gray-5"
      >
        {{ __("Images and videos") }}
        <span
          v-if="attachments.length"
          class="font-mono tabular-nums text-ink-gray-6"
        >
          {{ attachments.length }}
        </span>
      </h3>
      <template v-if="list.data?.can_upload">
        <Button
          size="sm"
          :label="__('Add')"
          :aria-describedby="hintId"
          @click="picker?.click()"
        >
          <template #prefix>
            <LucideImagePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <input
          ref="picker"
          type="file"
          multiple
          class="hidden"
          :accept="accept"
          @change="onPick"
        />
      </template>
    </div>

    <div
      v-if="list.loading && !list.data"
      role="status"
      :aria-label="__('Loading')"
      class="grid grid-cols-3 gap-2 sm:grid-cols-4"
    >
      <div
        v-for="i in 3"
        :key="i"
        aria-hidden="true"
        class="aspect-square animate-pulse rounded-lg bg-surface-gray-2"
      />
    </div>
    <div
      v-else-if="list.error"
      role="alert"
      class="flex flex-col items-start gap-2"
    >
      <p class="text-p-sm text-ink-gray-6">
        {{ errorText(list.error, __("Couldn't load the images and videos.")) }}
      </p>
      <Button :label="__('Retry')" @click="list.reload()">
        <template #prefix>
          <LucideRotateCw class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
    <template v-else-if="list.data">
      <ul
        v-if="queue.length"
        :aria-label="__('Uploads')"
        class="flex flex-col gap-1.5"
      >
        <li
          v-for="item in queue"
          :key="item.id"
          class="flex flex-col gap-1 rounded-md border border-outline-gray-2 px-3 py-2"
        >
          <div class="flex min-w-0 items-center gap-2 text-p-sm">
            <LucideCircleAlert
              v-if="item.error"
              class="size-4 shrink-0 text-danger"
              aria-hidden="true"
            />
            <LucideLoaderCircle
              v-else
              class="size-4 shrink-0 animate-spin text-ink-gray-6 motion-reduce:animate-none"
              aria-hidden="true"
            />
            <span class="min-w-0 flex-1 truncate text-ink-gray-8">{{
              item.name
            }}</span>
            <span
              v-if="!item.error"
              class="shrink-0 font-mono text-xs tabular-nums text-ink-gray-6"
              >{{ item.progress }}%</span
            >
            <button
              v-else
              type="button"
              class="touch-target flex size-6 shrink-0 items-center justify-center rounded text-ink-gray-6 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              :aria-label="__('Dismiss {0}', item.name)"
              @click="dismiss(item.id)"
            >
              <LucideX class="size-4" aria-hidden="true" />
            </button>
          </div>
          <p v-if="item.error" role="alert" class="text-p-sm text-danger">
            {{ item.error }}
          </p>
          <div
            v-else
            role="progressbar"
            :aria-label="__('Uploading {0}', item.name)"
            :aria-valuenow="item.progress"
            aria-valuemin="0"
            aria-valuemax="100"
            class="h-1 overflow-hidden rounded-full bg-surface-gray-2"
          >
            <div
              class="h-full rounded-full bg-brand transition-[width] motion-reduce:transition-none"
              :style="{ width: `${item.progress}%` }"
            />
          </div>
        </li>
      </ul>

      <p
        v-if="!attachments.length && !queue.length"
        class="text-p-sm text-ink-gray-5"
      >
        {{ __("No images or videos yet.") }}
        <template v-if="list.data.can_upload">
          {{ __("Add a screenshot or a screen recording to show the issue.") }}
        </template>
      </p>
      <ul
        v-else-if="attachments.length"
        class="grid grid-cols-3 gap-2 sm:grid-cols-4"
      >
        <li v-for="(item, i) in attachments" :key="item.name" class="min-w-0">
          <button
            type="button"
            class="group relative block aspect-square w-full overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            :aria-label="
              item.kind === 'video'
                ? __('Play {0}', item.file_name)
                : __('Open {0}', item.file_name)
            "
            @click="viewing = i"
          >
            <video
              v-if="item.kind === 'video'"
              :src="`${item.file_url}#t=0.1`"
              preload="metadata"
              muted
              playsinline
              tabindex="-1"
              aria-hidden="true"
              class="size-full object-cover"
            />
            <img
              v-else
              :src="item.file_url"
              :alt="item.file_name"
              loading="lazy"
              class="size-full object-cover transition-opacity group-hover:opacity-90"
            />
            <span
              v-if="item.kind === 'video'"
              class="absolute inset-0 flex items-center justify-center"
              aria-hidden="true"
            >
              <span
                class="flex size-9 items-center justify-center rounded-full bg-surface-gray-9/70 text-ink-base"
              >
                <LucidePlay class="size-4 translate-x-px" />
              </span>
            </span>
          </button>
        </li>
      </ul>
      <p
        v-if="list.data.can_upload"
        :id="hintId"
        class="text-p-xs text-ink-gray-5"
      >
        {{ limitsHint }}
      </p>
    </template>

    <MediaLightbox
      v-model:index="viewing"
      :items="attachments"
      :removing="remove.loading"
      @remove="(item) => remove.submit({ task, file: item.name })"
    />
  </section>
</template>

<script setup lang="ts">
import MediaLightbox, { type MediaItem } from "@/components/MediaLightbox.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, FileUploadHandler, createResource, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideImagePlus from "~icons/lucide/image-plus";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucidePlay from "~icons/lucide/play";
import LucideRotateCw from "~icons/lucide/rotate-cw";
import LucideX from "~icons/lucide/x";

interface TaskAttachment extends MediaItem {
  uploaded_by: string;
  creation: string;
}

interface AttachmentList {
  attachments: TaskAttachment[];
  can_upload: boolean;
  limits: Record<MediaItem["kind"], number>;
  extensions: Record<MediaItem["kind"], string[]>;
}

interface QueuedUpload {
  id: number;
  name: string;
  progress: number;
  error?: string;
}

const props = defineProps<{ task: string }>();
/** An image or video was added or removed: the activity has a new line. */
const emit = defineEmits<{ changed: [] }>();

const headingId = useId();
const hintId = useId();
const picker = ref<HTMLInputElement | null>(null);
const viewing = ref<number | null>(null);
const queue = ref<QueuedUpload[]>([]);
const dragging = ref(false);
let dragDepth = 0;
let nextId = 0;

const list = createResource({
  url: "helpdesk.api.task_attachments.list_task_attachments",
  makeParams: () => ({ task: props.task }),
  // shown in the section
  onError() {},
});
const data = computed(() => list.data as AttachmentList | undefined);
const attachments = computed(() => data.value?.attachments ?? []);
const extensions = computed(() => data.value?.extensions);
const accept = computed(() =>
  [...(extensions.value?.image ?? []), ...(extensions.value?.video ?? [])]
    .map((e) => `.${e}`)
    .join(",")
);

function typeList(kind: MediaItem["kind"]) {
  return (extensions.value?.[kind] ?? [])
    .map((e) => e.toUpperCase())
    .join(", ");
}

watch(
  () => props.task,
  (task) => {
    viewing.value = null;
    queue.value = [];
    if (task) list.reload();
  },
  { immediate: true }
);

function megabytes(bytes: number) {
  return String(Math.floor(bytes / 1024 / 1024));
}

const limitsHint = computed(() => {
  const limits = data.value?.limits;
  if (!limits) return "";
  return __(
    "Images ({0}) up to {1} MB, videos ({2}) up to {3} MB. You can also drop files here.",
    typeList("image"),
    megabytes(limits.image),
    typeList("video"),
    megabytes(limits.video)
  );
});

function extension(name: string) {
  return name.includes(".") ? name.split(".").pop()!.toLowerCase() : "";
}

/** Why the server would refuse the file, said before it is sent; null when it looks fine. */
function problem(file: File): string | null {
  const ext = extension(file.name);
  const d = data.value;
  const kind = (["image", "video"] as const).find((k) =>
    d?.extensions[k].includes(ext)
  );
  if (!d || !kind)
    return __(
      "{0} isn't an image or a video. Attach {1} or {2} files.",
      file.name,
      typeList("image"),
      typeList("video")
    );
  const limit = d.limits[kind];
  if (file.size > limit)
    return kind === "image"
      ? __(
          "{0} is over {1} MB. Crop it or save it as JPG and try again.",
          file.name,
          megabytes(limit)
        )
      : __(
          "{0} is over {1} MB. Trim the recording and try again.",
          file.name,
          megabytes(limit)
        );
  return null;
}

// one at a time, so a refused file is reported by name and the rest still upload
async function upload(files: File[]) {
  if (!data.value?.can_upload || !files.length) return;
  const items = files.map((file) => {
    const item: QueuedUpload = { id: nextId++, name: file.name, progress: 0 };
    const reason = problem(file);
    if (reason) item.error = reason;
    return { file, item };
  });
  queue.value.push(...items.map((i) => i.item));
  let added = 0;
  for (const { file, item } of items) {
    if (item.error) continue;
    // the reactive copy, so progress shows
    const row = queue.value.find((q) => q.id === item.id);
    if (!row) continue;
    const handler = new FileUploadHandler();
    handler.on("progress", (p: { uploaded: number; total: number }) => {
      row.progress = Math.round((p.uploaded / p.total) * 100);
    });
    try {
      await handler.upload(file, {
        upload_endpoint: `/api/method/helpdesk.api.task_attachments.upload_task_attachment?${new URLSearchParams(
          { task: props.task }
        )}`,
        private: true,
      });
      dismiss(row.id);
      added++;
    } catch (e: any) {
      row.error = e?.message || __("Couldn't upload {0}.", file.name);
    }
  }
  if (!added) return;
  toast.success(
    added === 1 ? __("1 file added") : __("{0} files added", String(added))
  );
  list.reload();
  emit("changed");
}

function dismiss(id: number) {
  queue.value = queue.value.filter((q) => q.id !== id);
}

function onPick(e: Event) {
  const input = e.target as HTMLInputElement;
  upload([...(input.files ?? [])]);
  input.value = "";
}

function hasFiles(e: DragEvent) {
  return !!e.dataTransfer?.types.includes("Files");
}

function onDragEnter(e: DragEvent) {
  if (!data.value?.can_upload || !hasFiles(e)) return;
  dragDepth++;
  dragging.value = true;
}

function onDragLeave() {
  dragDepth = Math.max(dragDepth - 1, 0);
  if (!dragDepth) dragging.value = false;
}

function onDrop(e: DragEvent) {
  dragDepth = 0;
  dragging.value = false;
  if (data.value?.can_upload) upload([...(e.dataTransfer?.files ?? [])]);
}

const remove = createResource({
  url: "helpdesk.api.task_attachments.delete_task_attachment",
  onSuccess() {
    toast.success(__("File removed"));
    const gone = remove.params?.file;
    list.setData((d: AttachmentList) => ({
      ...d,
      attachments: d.attachments.filter((a) => a.name !== gone),
    }));
    // stay on the one that took its place, or close when nothing is left
    const left = attachments.value.length;
    if (viewing.value !== null)
      viewing.value = left ? Math.min(viewing.value, left - 1) : null;
    emit("changed");
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't remove the file.")));
  },
});
</script>
