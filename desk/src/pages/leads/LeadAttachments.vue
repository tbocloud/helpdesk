<template>
  <section
    v-if="data?.available !== false"
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-labelledby="headingId"
  >
    <div
      class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 px-4 py-3"
    >
      <h2 :id="headingId" class="text-base font-semibold text-ink-gray-9">
        {{ __("Attachments") }}
        <span
          v-if="files.length"
          class="ml-1 font-mono text-xs tabular-nums text-ink-gray-5"
          >{{ files.length }}</span
        >
      </h2>
      <div v-if="canWrite && data" class="ml-auto">
        <Button :label="__('Attach')" :disabled="full" @click="picker?.click()">
          <template #prefix>
            <LucidePaperclip class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <input
          ref="picker"
          type="file"
          :accept="LEAD_FILE_ACCEPT"
          multiple
          class="hidden"
          tabindex="-1"
          aria-hidden="true"
          @change="onPick"
        />
      </div>
    </div>

    <div class="flex flex-col gap-3 px-4 py-3">
      <div
        v-if="list.loading && !data"
        role="status"
        :aria-label="__('Loading')"
        class="flex flex-col gap-2"
      >
        <div
          v-for="i in 2"
          :key="i"
          aria-hidden="true"
          class="h-10 animate-pulse rounded-md bg-surface-gray-2"
        />
      </div>
      <div
        v-else-if="list.error && !data"
        role="alert"
        class="flex flex-col items-start gap-2"
      >
        <p class="text-p-sm text-ink-gray-6">
          {{ errorText(list.error, __("Couldn't load the attachments.")) }}
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
          v-if="!files.length && !queue.length"
          class="text-p-sm text-ink-gray-6"
        >
          {{
            canWrite
              ? __(
                  "No files yet. Attach the client's requirement sheet, a quotation they sent or a visiting card."
                )
              : __("No files have been attached to this lead.")
          }}
        </p>
        <ul v-else-if="files.length" class="-mx-1 flex flex-col">
          <li
            v-for="file in files"
            :key="file.name"
            class="flex min-w-0 items-center gap-2 rounded-md px-1 py-1.5"
          >
            <component
              :is="fileIcon(file.file_name)"
              class="size-4 shrink-0 text-ink-gray-6"
              aria-hidden="true"
            />
            <div class="min-w-0 flex-1">
              <a
                :href="fileUrl(leadId, file)"
                target="_blank"
                rel="noopener"
                class="block truncate rounded text-sm text-ink-gray-8 underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                :title="file.file_name"
                >{{ file.file_name }}</a
              >
              <p class="truncate text-xs text-ink-gray-6">
                <span v-if="file.file_size" class="font-mono tabular-nums">{{
                  formatBytes(file.file_size)
                }}</span>
                <span v-if="file.file_size"> · </span>
                <span>{{ file.uploaded_by_name || file.uploaded_by }}</span>
                ·
                <time
                  :datetime="file.uploaded_on"
                  :title="dayjs(file.uploaded_on).format('D MMM YYYY, h:mm a')"
                  >{{ dayjs(file.uploaded_on).fromNow() }}</time
                >
              </p>
            </div>
            <template v-if="file.can_delete">
              <div
                v-if="confirming === file.name"
                class="flex shrink-0 items-center gap-1"
              >
                <Button
                  theme="red"
                  variant="subtle"
                  :label="__('Delete')"
                  :loading="remove.loading"
                  @click="remove.submit({ lead: leadId, file: file.name })"
                />
                <Button
                  variant="ghost"
                  :label="__('Keep')"
                  @click="confirming = null"
                />
              </div>
              <Button
                v-else
                variant="ghost"
                :aria-label="__('Delete {0}', file.file_name)"
                @click="confirming = file.name"
              >
                <LucideTrash2 class="size-4" aria-hidden="true" />
              </Button>
            </template>
          </li>
        </ul>
        <p v-if="canWrite && full" class="text-p-xs text-ink-gray-5">
          {{
            __(
              "A lead can have {0} files. Delete one to add another.",
              String(LEAD_FILE_LIMIT)
            )
          }}
        </p>
        <p v-else-if="canWrite" class="text-p-xs text-ink-gray-5">
          {{
            __(
              "PDF, Word, Excel, PowerPoint, CSV, text, pictures or ZIP, up to 10 MB each."
            )
          }}
        </p>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, createResource, dayjs, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucideTrash2 from "~icons/lucide/trash-2";
import LucideX from "~icons/lucide/x";
import { fileIcon, formatBytes } from "../tasky/projectFiles";
import {
  attachable,
  LEAD_FILE_ACCEPT,
  LEAD_FILE_LIMIT,
  leadFileUrl,
} from "./leadFiles";
import { readBase64 } from "./place";

/** One file of a lead as get_lead_files lists it. */
interface LeadFile {
  name: string;
  file_name: string;
  file_size?: number;
  uploaded_by: string;
  uploaded_by_name?: string;
  uploaded_on: string;
  can_delete: boolean;
}

interface QueuedUpload {
  id: number;
  name: string;
  waiting: boolean;
  error?: string;
}

const props = defineProps<{ leadId: string; canWrite: boolean }>();

const headingId = useId();
const picker = ref<HTMLInputElement | null>(null);
const queue = ref<QueuedUpload[]>([]);
const notice = ref("");
const confirming = ref<string | null>(null);
let nextId = 0;

const list = createResource({
  url: "helpdesk.api.leads.get_lead_files",
  makeParams: () => ({ lead: props.leadId }),
  // shown in the card
  onError() {},
});
const data = computed(
  () => list.data as { available: boolean; files: LeadFile[] } | undefined
);
const files = computed(() => data.value?.files ?? []);
const full = computed(
  () => files.value.length + queue.value.length >= LEAD_FILE_LIMIT
);

watch(
  () => props.leadId,
  () => {
    queue.value = [];
    notice.value = "";
    confirming.value = null;
    list.reload();
  },
  { immediate: true }
);

function fileUrl(lead: string, file: LeadFile) {
  return leadFileUrl(lead, file.name, file.file_name);
}

function onPick(event: Event) {
  const input = event.target as HTMLInputElement;
  const chosen = [...(input.files ?? [])];
  input.value = "";
  const refused: string[] = [];
  const room = LEAD_FILE_LIMIT - files.value.length - queue.value.length;
  const accepted = chosen.filter((f) => {
    const ok = attachable(f);
    if (!ok) refused.push(f.name);
    return ok;
  });
  const messages: string[] = [];
  if (refused.length)
    messages.push(
      __(
        "Left out {0}: only PDF, Word, Excel, PowerPoint, CSV, text, pictures or ZIP of at most 10 MB can be attached.",
        refused.join(", ")
      )
    );
  if (accepted.length > room)
    messages.push(
      __(
        "A lead can have {0} files, so only the first {1} were taken.",
        String(LEAD_FILE_LIMIT),
        String(Math.max(room, 0))
      )
    );
  notice.value = messages.join(" ");
  send(accepted.slice(0, Math.max(room, 0)));
}

function dismiss(id: number) {
  queue.value = queue.value.filter((q) => q.id !== id);
}

// one at a time, so a refused file is reported by name and the rest still go
async function send(chosen: File[]) {
  if (!chosen.length) return;
  const lead = props.leadId;
  const rows = chosen.map((file) => {
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
      await call("helpdesk.api.leads.upload_lead_file", {
        lead,
        filename: file.name,
        content: await readBase64(file),
      });
      dismiss(id);
      added++;
    } catch (e) {
      row.error = errorText(e, __("Couldn't attach {0}.", file.name));
    }
  }
  if (!added) return;
  toast.success(
    added === 1
      ? __("1 file attached")
      : __("{0} files attached", String(added))
  );
  if (lead === props.leadId) list.reload();
}

const remove = createResource({
  url: "helpdesk.api.leads.delete_lead_file",
  method: "POST",
  onSuccess() {
    toast.success(__("File deleted"));
    const gone = remove.params?.file;
    confirming.value = null;
    list.setData((d: { available: boolean; files: LeadFile[] }) => ({
      ...d,
      files: d.files.filter((f) => f.name !== gone),
    }));
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't delete the file. Try again.")));
  },
});
</script>
