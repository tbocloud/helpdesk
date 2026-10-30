<template>
  <section
    v-if="data?.available !== false"
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-labelledby="headingId"
  >
    <div
      class="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 px-4 py-3"
    >
      <h2 :id="headingId" class="text-base-medium text-ink-gray-9">
        {{ __("Photos") }}
        <span
          v-if="photos.length"
          class="ml-1 font-mono text-xs tabular-nums text-ink-gray-5"
          >{{ photos.length }}/{{ LEAD_PHOTO_LIMIT }}</span
        >
      </h2>
      <div v-if="canWrite && data" class="ml-auto flex gap-2">
        <Button
          :label="__('Take photo')"
          :disabled="full"
          @click="camera?.click()"
        >
          <template #prefix>
            <LucideCamera class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          :label="__('Add photos')"
          :disabled="full"
          @click="gallery?.click()"
        >
          <template #prefix>
            <LucideImagePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <!-- two pickers: `capture` opens the camera only, so the gallery needs its own -->
        <input
          ref="camera"
          type="file"
          accept="image/*"
          capture="environment"
          class="hidden"
          tabindex="-1"
          aria-hidden="true"
          @change="onPick"
        />
        <input
          ref="gallery"
          type="file"
          accept="image/*"
          multiple
          class="hidden"
          tabindex="-1"
          aria-hidden="true"
          @change="onPick"
        />
      </div>
    </div>

    <div class="flex flex-col gap-3 px-4 py-4">
      <div
        v-if="list.loading && !data"
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
        v-else-if="list.error && !data"
        role="alert"
        class="flex flex-col items-start gap-2"
      >
        <p class="text-p-sm text-ink-gray-6">
          {{ errorText(list.error, __("Couldn't load the photos.")) }}
        </p>
        <Button :label="__('Try again')" @click="list.reload()" />
      </div>
      <template v-else>
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
                class="shrink-0 text-xs text-ink-gray-6"
                >{{ item.waiting ? __("Waiting") : __("Uploading") }}</span
              >
              <button
                v-else
                type="button"
                class="flex size-8 shrink-0 items-center justify-center rounded text-ink-gray-6 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                :aria-label="__('Dismiss {0}', item.name)"
                @click="dismiss(item.id)"
              >
                <LucideX class="size-4" aria-hidden="true" />
              </button>
            </div>
            <p v-if="item.error" role="alert" class="text-p-sm text-danger">
              {{ item.error }}
            </p>
          </li>
        </ul>

        <p v-if="notice" role="alert" class="text-p-sm text-danger">
          {{ notice }}
        </p>

        <p
          v-if="!photos.length && !queue.length"
          class="text-p-sm text-ink-gray-6"
        >
          {{
            canWrite
              ? __(
                  "No photos yet. Add the shop or office front, the visiting card or the site, so whoever visits can recognise the place."
                )
              : __("No photos have been added to this lead.")
          }}
        </p>
        <ul
          v-else-if="photos.length"
          class="grid grid-cols-3 gap-2 sm:grid-cols-4"
        >
          <li v-for="(photo, i) in photos" :key="photo.name" class="min-w-0">
            <button
              type="button"
              class="group relative block aspect-square w-full overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              :aria-label="__('Open {0}', label(photo))"
              @click="viewing = i"
            >
              <img
                :src="photoUrl(leadId, photo.name, true)"
                :alt="label(photo)"
                loading="lazy"
                class="size-full object-cover transition-opacity group-hover:opacity-90"
              />
            </button>
          </li>
        </ul>
        <p v-if="canWrite && full" class="text-p-xs text-ink-gray-5">
          {{
            __(
              "A lead can have {0} photos. Delete one to add another.",
              String(LEAD_PHOTO_LIMIT)
            )
          }}
        </p>
      </template>
    </div>

    <Dialog
      :open="staged.length > 0"
      :title="__('Add photos')"
      size="md"
      @update:open="(v: boolean) => !v && clearStaged()"
    >
      <form
        :id="formId"
        class="flex flex-col gap-4"
        novalidate
        @submit.prevent="send"
      >
        <ul class="grid grid-cols-4 gap-2" :aria-label="__('Chosen photos')">
          <li v-for="item in staged" :key="item.url" class="min-w-0">
            <img
              :src="item.url"
              :alt="item.file.name"
              class="aspect-square w-full rounded-md border border-outline-gray-2 object-cover"
            />
          </li>
        </ul>
        <FormControl
          v-model="caption"
          :label="__('Caption (optional)')"
          :placeholder="__('Shop front, visiting card, parking')"
          maxlength="140"
        />
      </form>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button type="button" :label="__('Cancel')" @click="clearStaged" />
          <Button
            variant="solid"
            type="submit"
            :form="formId"
            :label="
              staged.length === 1
                ? __('Add photo')
                : __('Add {0} photos', String(staged.length))
            "
          />
        </div>
      </template>
    </Dialog>

    <MediaLightbox
      v-model:index="viewing"
      :items="items"
      :removing="remove.loading"
      @remove="(item) => remove.submit({ lead: leadId, file: item.name })"
    />
  </section>
</template>

<script setup lang="ts">
import MediaLightbox, { type MediaItem } from "@/components/MediaLightbox.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  createResource,
  Dialog,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, onBeforeUnmount, ref, useId, watch } from "vue";
import LucideCamera from "~icons/lucide/camera";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideImagePlus from "~icons/lucide/image-plus";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucideX from "~icons/lucide/x";
import {
  LEAD_PHOTO_LIMIT,
  photoUrl,
  preparePhoto,
  type LeadPhoto,
} from "./place";

interface QueuedUpload {
  id: number;
  name: string;
  waiting: boolean;
  error?: string;
}

const props = defineProps<{ leadId: string; canWrite: boolean }>();

const headingId = useId();
const formId = `lead-photos-${useId()}`;
const camera = ref<HTMLInputElement | null>(null);
const gallery = ref<HTMLInputElement | null>(null);
const viewing = ref<number | null>(null);
const queue = ref<QueuedUpload[]>([]);
const staged = ref<{ file: File; url: string }[]>([]);
const caption = ref("");
const notice = ref("");
let nextId = 0;

const list = createResource({
  url: "helpdesk.api.leads.get_lead_photos",
  makeParams: () => ({ lead: props.leadId }),
  // shown in the card
  onError() {},
});
const data = computed(
  () => list.data as { available: boolean; photos: LeadPhoto[] } | undefined
);
const photos = computed(() => data.value?.photos ?? []);
const full = computed(
  () => photos.value.length + queue.value.length >= LEAD_PHOTO_LIMIT
);

watch(
  () => props.leadId,
  () => {
    viewing.value = null;
    queue.value = [];
    clearStaged();
    list.reload();
  },
  { immediate: true }
);

const label = (photo: LeadPhoto) =>
  photo.caption ||
  __("Photo from {0}", photo.uploaded_by_name || photo.uploaded_by);

const items = computed<MediaItem[]>(() =>
  photos.value.map((photo) => ({
    name: photo.name,
    file_name: label(photo),
    file_url: photoUrl(props.leadId, photo.name),
    file_size: photo.file_size,
    kind: "image",
    uploaded_by_name: photo.uploaded_by_name,
    // the ERP site decides who may delete, and says so if it refuses
    can_delete: props.canWrite,
  }))
);

function onPick(event: Event) {
  const input = event.target as HTMLInputElement;
  const chosen = [...(input.files ?? [])];
  input.value = "";
  notice.value = "";
  const images = chosen.filter(
    (f) => f.type.startsWith("image/") || /\.(heic|heif)$/i.test(f.name)
  );
  if (images.length < chosen.length)
    notice.value = __("Only pictures can be added. Others were left out.");
  const room = LEAD_PHOTO_LIMIT - photos.value.length - queue.value.length;
  if (images.length > room) {
    notice.value = __(
      "A lead can have {0} photos, so only the first {1} were taken.",
      String(LEAD_PHOTO_LIMIT),
      String(Math.max(room, 0))
    );
  }
  clearStaged();
  staged.value = images
    .slice(0, Math.max(room, 0))
    .map((file) => ({ file, url: URL.createObjectURL(file) }));
}

function clearStaged() {
  staged.value.forEach((s) => URL.revokeObjectURL(s.url));
  staged.value = [];
  caption.value = "";
}
onBeforeUnmount(clearStaged);

function dismiss(id: number) {
  queue.value = queue.value.filter((q) => q.id !== id);
}

// one at a time, so a refused photo is reported by name and the rest still go
async function send() {
  const files = staged.value.map((s) => s.file);
  const text = caption.value.trim();
  const lead = props.leadId;
  clearStaged();
  const rows = files.map((file) => {
    const row: QueuedUpload = { id: nextId++, name: file.name, waiting: true };
    queue.value.push(row);
    return { file, id: row.id };
  });
  let added = 0;
  for (const { file, id } of rows) {
    const row = queue.value.find((q) => q.id === id);
    if (!row) continue;
    row.waiting = false;
    try {
      const photo = await preparePhoto(file);
      await call("helpdesk.api.leads.upload_lead_photo", {
        lead,
        filename: photo.filename,
        content: photo.content,
        caption: text || null,
      });
      dismiss(id);
      added++;
    } catch (e) {
      row.error = errorText(e, __("Couldn't upload {0}.", file.name));
    }
  }
  if (!added) return;
  toast.success(
    added === 1 ? __("1 photo added") : __("{0} photos added", String(added))
  );
  if (lead === props.leadId) list.reload();
}

const remove = createResource({
  url: "helpdesk.api.leads.delete_lead_photo",
  method: "POST",
  onSuccess() {
    toast.success(__("Photo deleted"));
    const gone = remove.params?.file;
    list.setData((d: { available: boolean; photos: LeadPhoto[] }) => ({
      ...d,
      photos: d.photos.filter((p) => p.name !== gone),
    }));
    // stay on the one that took its place, or close when nothing is left
    const left = photos.value.length;
    if (viewing.value !== null)
      viewing.value = left ? Math.min(viewing.value, left - 1) : null;
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't delete the photo. Try again.")));
  },
});
</script>
