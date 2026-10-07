<template>
  <Dialog
    :open="!!file"
    :title="file?.file_name || ''"
    size="4xl"
    @update:open="(v: boolean) => !v && emit('update:file', null)"
  >
    <div v-if="file" class="flex flex-col gap-3">
      <div
        class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-gray-6"
      >
        <span>{{ __("Added by {0}", file.uploaded_by_name) }}</span>
        <span class="font-mono tabular-nums">{{
          formatBytes(file.file_size)
        }}</span>
        <span v-if="file.for_users.length">
          {{ __("For {0}", file.for_users.map((p) => p.full_name).join(", ")) }}
        </span>
      </div>

      <template v-if="kind === 'markdown' || kind === 'text'">
        <div
          v-if="text.loading && !text.data"
          class="flex flex-col gap-2"
          aria-busy="true"
        >
          <div
            v-for="i in 5"
            :key="i"
            class="h-3.5 animate-pulse rounded bg-surface-gray-2"
            :style="{ width: `${90 - i * 9}%` }"
          />
        </div>
        <div
          v-else-if="text.error"
          role="alert"
          class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
        >
          <LucideCircleAlert
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <span>{{
            errorText(text.error, __("Couldn't open this file."))
          }}</span>
        </div>
        <div
          v-else-if="kind === 'markdown'"
          class="prose prose-sm max-h-[65vh] max-w-none overflow-y-auto rounded-lg border border-outline-gray-2 bg-surface-base px-5 py-4 text-ink-gray-8"
          v-html="rendered"
        />
        <pre
          v-else
          class="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-4 py-3 font-mono text-p-sm text-ink-gray-8"
          >{{ text.data?.content }}</pre
        >
      </template>

      <iframe
        v-else-if="kind === 'pdf'"
        :src="file.file_url"
        :title="file.file_name"
        class="h-[70vh] w-full rounded-lg border border-outline-gray-2 bg-surface-gray-1"
      />

      <div
        v-else-if="kind === 'image'"
        class="flex max-h-[70vh] justify-center overflow-auto rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-2"
      >
        <img
          :src="file.file_url"
          :alt="file.file_name"
          class="max-h-[68vh] object-contain"
        />
      </div>
    </div>

    <template #actions>
      <div v-if="file" class="flex flex-wrap items-center justify-end gap-2">
        <Button
          v-if="isText"
          :label="copied ? __('Copied') : __('Copy text')"
          :disabled="!text.data"
          @click="copyText"
        >
          <template #prefix>
            <component
              :is="copied ? LucideCheck : LucideCopy"
              class="size-4"
              aria-hidden="true"
            />
          </template>
        </Button>
        <Button
          v-if="kind === 'pdf'"
          :label="__('Open in new tab')"
          :link="file.file_url"
        >
          <template #prefix>
            <LucideExternalLink class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <a
          :href="downloadHref(file.file_url)"
          :download="file.file_name"
          class="inline-flex h-7 items-center gap-1.5 rounded bg-surface-gray-2 px-2 text-base text-ink-gray-8 transition-colors hover:bg-surface-gray-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          <LucideDownload class="size-4" aria-hidden="true" />
          {{ __("Download") }}
        </a>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, Dialog, createResource, toast } from "frappe-ui";
import { marked } from "marked";
import sanitizeHtml from "sanitize-html";
import { computed, ref, watch } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCopy from "~icons/lucide/copy";
import LucideDownload from "~icons/lucide/download";
import LucideExternalLink from "~icons/lucide/external-link";
import {
  downloadHref,
  fileKind,
  formatBytes,
  type ProjectFile,
} from "../projectFiles";
import { errorText } from "../taskMeta";

const props = defineProps<{
  /** The file to show; the dialog is open while this is set. */
  file: ProjectFile | null;
  projectId: string;
}>();

const emit = defineEmits<{ "update:file": [value: null] }>();

const kind = computed(() => (props.file ? fileKind(props.file.file_name) : ""));
const isText = computed(
  () => kind.value === "markdown" || kind.value === "text"
);
const copied = ref(false);

const text = createResource({
  url: "helpdesk.api.project_files.get_project_file_text",
  makeParams: () => ({ project: props.projectId, file: props.file?.name }),
  // shown inside the dialog
  onError() {},
});

watch(
  () => props.file?.name,
  (name) => {
    copied.value = false;
    text.reset();
    if (name && isText.value) text.reload();
  },
  { immediate: true }
);

// files are user content: render the Markdown, then keep only harmless markup
const rendered = computed(() => {
  const raw = text.data?.content;
  if (!raw) return "";
  const html = marked.parse(raw, { gfm: true, async: false }) as string;
  return sanitizeHtml(html, {
    allowedTags: sanitizeHtml.defaults.allowedTags.concat(["del", "input"]),
    allowedAttributes: {
      a: ["href", "title", "target", "rel"],
      code: ["class"],
      input: ["type", "checked", "disabled"],
      th: ["align"],
      td: ["align"],
    },
    allowedSchemes: ["http", "https", "mailto"],
    transformTags: {
      a: sanitizeHtml.simpleTransform("a", {
        target: "_blank",
        rel: "noopener noreferrer",
      }),
    },
    exclusiveFilter: (frame) =>
      frame.tag === "input" && frame.attribs.type !== "checkbox",
  });
});

/** Copy the previewed text file's content to the clipboard. */
async function copyText() {
  try {
    await navigator.clipboard.writeText(text.data?.content ?? "");
    copied.value = true;
    setTimeout(() => (copied.value = false), 2000);
  } catch {
    toast.error(__("Couldn't copy. Select the text and copy it instead."));
  }
}
</script>
