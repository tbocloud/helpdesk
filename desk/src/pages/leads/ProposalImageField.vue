<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-wrap items-start gap-3">
      <img
        v-if="block.image_url"
        :src="block.image_url"
        :alt="block.image_alt || ''"
        class="h-24 w-36 rounded-lg border border-outline-gray-2 bg-surface-gray-1 object-cover"
      />
      <div
        v-else
        class="flex h-24 w-36 items-center justify-center rounded-lg border border-dashed border-outline-gray-3 text-ink-gray-5"
      >
        <LucideImage class="size-5" aria-hidden="true" />
        <span class="sr-only">{{ __("No image") }}</span>
      </div>
      <div class="flex flex-col gap-2">
        <span class="text-xs text-ink-gray-5">{{
          isCover
            ? __("Cover image (optional)")
            : block.section_type === "Image"
            ? __("Image")
            : __("Image (optional)")
        }}</span>
        <div v-if="editable" class="flex flex-wrap gap-2">
          <Button
            :label="block.image ? __('Replace') : __('Upload image')"
            :loading="upload.loading"
            @click="input?.click()"
          >
            <template #prefix>
              <LucideUpload class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <Button
            v-if="libraryImages.length"
            :label="__('From the library')"
            @click="showLibrary = true"
          >
            <template #prefix>
              <LucideImages class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <Button
            v-if="block.image"
            variant="ghost"
            :label="__('Remove')"
            @click="emit('update', { image: null, image_url: null })"
          />
        </div>
        <p class="text-p-xs text-ink-gray-5">
          {{ __("PNG, JPEG or WebP, up to 5 MB.") }}
        </p>
        <input
          ref="input"
          type="file"
          class="hidden"
          :accept="ACCEPT.join(',')"
          tabindex="-1"
          aria-hidden="true"
          @change="pick"
        />
      </div>
    </div>
    <p v-if="error" role="alert" class="text-p-sm text-danger">{{ error }}</p>
    <Dialog
      v-model:open="showLibrary"
      :title="__('Choose an image')"
      size="2xl"
    >
      <ul class="grid grid-cols-2 gap-3 sm:grid-cols-3" role="list">
        <li v-for="img in libraryImages" :key="img.name">
          <button
            type="button"
            class="flex w-full flex-col gap-1 rounded-lg border border-outline-gray-2 p-2 text-left hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight disabled:opacity-60"
            :disabled="fromLibrary.loading"
            @click="fromLibrary.submit({ name: proposal, image: img.name })"
          >
            <img
              :src="img.url || ''"
              :alt="img.alt_text"
              class="h-24 w-full rounded object-cover"
            />
            <span class="truncate text-sm text-ink-gray-8">{{
              img.title
            }}</span>
            <span
              v-if="img.sections.includes(block.section_type)"
              class="text-xs text-ink-gray-5"
              >{{ __("Suits this section") }}</span
            >
          </button>
        </li>
      </ul>
    </Dialog>
    <template v-if="block.image">
      <FormControl
        :model-value="block.image_alt || ''"
        :label="__('Alt text')"
        :description="
          __('What the image shows, for people who can\'t see it. Required.')
        "
        maxlength="140"
        required
        :disabled="!editable"
        @update:model-value="emit('update', { image_alt: $event })"
      />
      <div
        v-if="!isCover"
        class="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto]"
      >
        <FormControl
          :model-value="block.image_caption || ''"
          :label="__('Caption (optional)')"
          maxlength="280"
          :disabled="!editable"
          @update:model-value="emit('update', { image_caption: $event })"
        />
        <div class="flex flex-col gap-1.5">
          <span :id="sizeLabelId" class="text-xs text-ink-gray-5">{{
            __("Width")
          }}</span>
          <TabButtons
            :model-value="block.image_size || 'Full'"
            :aria-labelledby="sizeLabelId"
            :options="sizeOptions"
            @update:model-value="
              editable && emit('update', { image_size: $event })
            "
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  Dialog,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, ref, useId } from "vue";
import LucideImages from "~icons/lucide/images";
import LucideImage from "~icons/lucide/image";
import LucideUpload from "~icons/lucide/upload";
import {
  proposalOptions,
  type ProposalOptions,
  type ProposalSection,
} from "./proposals";

const props = defineProps<{
  proposal: string;
  block: ProposalSection;
  editable: boolean;
}>();
const emit = defineEmits<{
  (e: "update", patch: Partial<ProposalSection>): void;
}>();

// the ERP site decides by the bytes; this only spares a pointless upload
const ACCEPT = ["image/png", "image/jpeg", "image/webp"];
const MAX_BYTES = 5 * 1024 * 1024;

const input = ref<HTMLInputElement>();
const error = ref("");
const sizeLabelId = `proposal-image-size-${useId()}`;
const isCover = computed(() => props.block.section_type === "Cover");
const sizeOptions = [
  { label: __("Full"), value: "Full" },
  { label: __("Half"), value: "Half" },
];

const showLibrary = ref(false);
/** The library's images, those tagged for this section first. */
const libraryImages = computed(() => {
  const all =
    (proposalOptions.data as ProposalOptions | undefined)?.images ?? [];
  const suits = (img: typeof all[number]) =>
    img.sections.includes(props.block.section_type) ? 0 : 1;
  return [...all].sort((a, b) => suits(a) - suits(b));
});

const fromLibrary = createResource({
  url: "helpdesk.api.proposals.use_library_image",
  method: "POST",
  onSuccess(d: { file: string; url: string; alt?: string }) {
    emit("update", {
      image: d.file,
      image_url: d.url,
      image_alt: props.block.image_alt || d.alt || "",
    });
    showLibrary.value = false;
  },
  onError(e: unknown) {
    error.value = errorText(e, __("Couldn't use that image. Try another."));
    showLibrary.value = false;
  },
});

const upload = createResource({
  url: "helpdesk.api.proposals.upload_proposal_image",
  method: "POST",
  onSuccess(d: { file: string; url: string }) {
    emit("update", { image: d.file, image_url: d.url });
  },
  onError(e: unknown) {
    error.value = errorText(e, __("Couldn't upload the image. Try again."));
  },
});

function base64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function pick(event: Event) {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  target.value = "";
  if (!file) return;
  error.value = "";
  if (!ACCEPT.includes(file.type)) {
    error.value = __("Upload a PNG, JPEG or WebP image.");
    return;
  }
  if (file.size > MAX_BYTES) {
    error.value = __(
      "The image is larger than 5 MB. Make it smaller and try again."
    );
    return;
  }
  try {
    upload.submit({
      name: props.proposal,
      filename: file.name,
      content: await base64(file),
    });
  } catch {
    error.value = __("Couldn't read that file.");
  }
}
</script>
