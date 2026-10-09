<template>
  <Dialog v-model:open="open" :options="{ size: '2xl' }" :dismissible="false">
    <template #body-title>
      <div class="flex items-center gap-2">
        <h3 class="text-xl-semibold text-ink-gray-9">
          {{ isNew ? __("New post") : form.title || __("Post") }}
        </h3>
        <span v-if="!isNew" class="font-mono text-xs text-ink-gray-5">{{
          post?.name
        }}</span>
      </div>
    </template>
    <template #body-content>
      <div v-if="loading" class="flex flex-col gap-3 py-2">
        <div
          v-for="i in 4"
          :key="i"
          class="h-8 animate-pulse rounded bg-surface-gray-2"
        />
      </div>
      <form
        v-else
        id="content-post-form"
        class="flex flex-col gap-4"
        @submit.prevent="save"
      >
        <div
          v-if="approvalNote"
          class="flex items-start gap-2 rounded-lg px-3 py-2.5 text-p-sm"
          :class="approvalNote.tone"
          role="status"
        >
          <component
            :is="approvalNote.icon"
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <div>
            <div class="font-medium">{{ approvalNote.title }}</div>
            <div v-if="approvalNote.body" class="whitespace-pre-line">
              {{ approvalNote.body }}
            </div>
          </div>
        </div>
        <!-- only editors change the entry; anyone who can open it adds files below -->
        <fieldset
          :disabled="!canEdit"
          class="flex min-w-0 flex-col gap-4 disabled:opacity-80"
        >
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Link
              v-model="form.customer"
              doctype="HD Customer"
              :label="__('Customer') + ' *'"
              :placeholder="__('Select customer')"
            />
            <FormControl
              v-model="form.campaign"
              :label="__('Campaign (optional)')"
              :placeholder="__('e.g. Diwali 2026')"
              maxlength="140"
            />
            <fieldset class="flex flex-col gap-1.5 sm:col-span-2">
              <legend class="mb-1.5 text-xs text-ink-gray-5">
                {{ __("Platforms") }} ·
                <span>{{ __("this one post goes out on each") }}</span>
              </legend>
              <div class="flex flex-wrap gap-1.5">
                <ChipToggle
                  v-for="channel in platformOptions"
                  :key="channel"
                  :label="channel"
                  :pressed="platforms.includes(channel)"
                  @toggle="togglePlatform(channel)"
                >
                  <template #icon>
                    <ChannelIcon :channel="channel" class="size-4 shrink-0" />
                  </template>
                </ChipToggle>
                <AddOptionChip
                  kind="platform"
                  :label="__('Add platform')"
                  :placeholder="__('e.g. Threads')"
                  @added="addPlatform"
                />
              </div>
            </fieldset>
            <fieldset class="flex flex-col gap-1.5 sm:col-span-2">
              <legend class="mb-1.5 text-xs text-ink-gray-5">
                {{ __("Post type") }}
              </legend>
              <div class="flex flex-wrap gap-1.5" role="radiogroup">
                <ChipToggle
                  v-for="format in postTypes"
                  :key="format"
                  :label="format"
                  role="radio"
                  :pressed="form.format === format"
                  @toggle="form.format = format"
                >
                  <template #icon>
                    <PostTypeIcon :post-type="format" class="size-4 shrink-0" />
                  </template>
                </ChipToggle>
                <AddOptionChip
                  kind="postType"
                  :label="__('Add post type')"
                  :placeholder="__('e.g. Infographic')"
                  @added="(name) => (form.format = name)"
                />
              </div>
            </fieldset>
            <FormControl
              v-model="form.status"
              type="select"
              :label="__('Status')"
              :options="STATUSES"
            />
            <FormControl
              v-model="form.publish_on"
              type="datetime-local"
              :label="__('Publish on') + ' *'"
              required
            />
            <FormControl
              v-model="form.special_day"
              class="sm:col-span-2"
              :label="__('Special day (optional)')"
              :placeholder="__('e.g. Diwali, Brand anniversary')"
              :description="__('Highlighted on the calendar.')"
              maxlength="140"
            />
          </div>
          <FormControl
            v-model="form.title"
            :label="__('Copy')"
            :placeholder="__('e.g. Diwali offer carousel')"
            required
          />
          <div class="flex flex-col gap-1.5">
            <div class="flex items-center justify-between gap-2">
              <label for="post-caption" class="text-xs text-ink-gray-5">{{
                __("Sub Copy")
              }}</label>
              <div class="flex items-center gap-2">
                <button
                  v-if="undoAi"
                  type="button"
                  class="text-xs text-ink-gray-5 underline-offset-2 hover:text-ink-gray-8 hover:underline"
                  @click="revertAi"
                >
                  {{ __("Undo") }}
                </button>
                <button
                  type="button"
                  class="inline-flex h-7 items-center gap-1.5 rounded-md bg-brand-soft px-2.5 text-sm font-medium text-brand-ink transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
                  :disabled="drafting"
                  :aria-busy="drafting"
                  @click="draftWithAi"
                >
                  <LucideLoaderCircle
                    v-if="drafting"
                    class="size-4 animate-spin"
                    aria-hidden="true"
                  />
                  <LucideSparkles v-else class="size-4" aria-hidden="true" />
                  {{
                    form.caption.trim()
                      ? __("Improve with AI")
                      : __("Draft with AI")
                  }}
                </button>
              </div>
            </div>
            <FormControl
              v-model="aiBrief"
              :placeholder="
                __(
                  'Brief for AI (optional), e.g. 20% off until 5 Nov, family audience'
                )
              "
              :aria-label="__('Brief for AI')"
            />
            <FormControl
              id="post-caption"
              v-model="form.caption"
              type="textarea"
              :rows="6"
              :placeholder="__('Write the caption…')"
            />
            <p v-if="aiError" class="text-xs text-danger" role="alert">
              {{ aiError }}
            </p>
          </div>
          <FormControl
            v-model="form.brief"
            type="textarea"
            :rows="2"
            :label="__('Description')"
            :placeholder="__('What should the design or video look like?')"
            :description="__('Internal only. The client never sees this.')"
          />
          <FormControl
            v-model="form.hashtags"
            :label="__('Hashtags')"
            :placeholder="__('#diwali #offers')"
          />
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <RoleHoursField
              v-for="role in TEAM_ROLES"
              :key="role.field"
              v-model:people="team[role.field]"
              v-model:hours="form[`${role.field}_hours`]"
              :label="__(role.label)"
            />
          </div>
        </fieldset>
        <div
          class="flex flex-col gap-1.5 rounded-lg transition-colors"
          :class="dragging ? 'bg-brand-soft ring-2 ring-brand' : ''"
          @dragover.prevent="!isNew && (dragging = true)"
          @dragleave.self="dragging = false"
          @drop.prevent="onDrop"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs text-ink-gray-5">{{ __("Attachments") }}</span>
            <div v-if="!isNew" class="flex items-center gap-1.5">
              <Button
                v-if="(attachments.data?.length ?? 0) > 1"
                size="sm"
                variant="ghost"
                :label="__('Download all')"
                :tooltip="
                  __(
                    'All {0} files as one .zip',
                    String(attachments.data.length)
                  )
                "
                @click="downloadAll"
              >
                <template #prefix
                  ><LucideDownload class="size-4" aria-hidden="true"
                /></template>
              </Button>
              <input
                ref="fileInput"
                type="file"
                multiple
                :accept="ACCEPT"
                class="hidden"
                @change="onPick"
              />
              <Button
                size="sm"
                :loading="!!uploading"
                :label="
                  uploading
                    ? __(
                        'Uploading {0} of {1}',
                        String(uploading.done + 1),
                        String(uploading.total)
                      )
                    : __('Add files')
                "
                @click="fileInput?.click()"
              >
                <template #prefix
                  ><LucidePaperclip class="size-4" aria-hidden="true"
                /></template>
              </Button>
            </div>
          </div>
          <p v-if="isNew" class="text-p-sm text-ink-gray-5">
            {{
              __("Create the post first, then add its designs and files here.")
            }}
          </p>
          <p
            v-else-if="!attachments.data?.length"
            class="rounded-lg border border-dashed border-outline-gray-3 px-3 py-5 text-center text-p-sm text-ink-gray-5"
          >
            {{
              __(
                "Drop files here or use Add files. You can pick several at once. Images are sent to the client with the approval request."
              )
            }}
          </p>
          <template v-else>
            <ul
              v-if="imageFiles.length"
              class="grid grid-cols-3 gap-2 sm:grid-cols-4"
              role="list"
            >
              <li
                v-for="img in imageFiles"
                :key="img.name"
                class="group relative aspect-square overflow-hidden rounded-lg border border-outline-gray-2"
              >
                <a :href="img.file_url" target="_blank" rel="noopener">
                  <img
                    :src="img.file_url"
                    :alt="img.file_name"
                    class="size-full object-cover"
                    loading="lazy"
                  />
                </a>
                <!-- always shown on touch screens, on hover / focus elsewhere -->
                <div
                  class="absolute right-1 top-1 flex gap-1 transition sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
                >
                  <a
                    :href="downloadHref(img.file_url)"
                    :download="img.file_name"
                    class="grid size-6 place-items-center rounded-md bg-surface-base/90 text-ink-gray-7 shadow-sm hover:text-ink-gray-9"
                    :aria-label="__('Download {0}', img.file_name)"
                    :title="__('Download')"
                  >
                    <LucideDownload class="size-3.5" aria-hidden="true" />
                  </a>
                  <button
                    v-if="canRemove(img)"
                    type="button"
                    class="grid size-6 place-items-center rounded-md bg-surface-base/90 text-ink-gray-7 shadow-sm hover:text-danger"
                    :aria-label="__('Remove {0}', img.file_name)"
                    :title="__('Remove')"
                    @click="removeFile(img.name)"
                  >
                    <LucideX class="size-3.5" aria-hidden="true" />
                  </button>
                </div>
              </li>
            </ul>
            <ul
              v-if="otherFiles.length"
              class="flex flex-col gap-1.5"
              role="list"
            >
              <li
                v-for="f in otherFiles"
                :key="f.name"
                class="flex items-center gap-2 rounded-lg border border-outline-gray-2 px-3 py-2"
              >
                <LucideFileText
                  class="size-4 shrink-0 text-ink-gray-5"
                  aria-hidden="true"
                />
                <a
                  :href="f.file_url"
                  target="_blank"
                  rel="noopener"
                  class="min-w-0 flex-1 truncate text-sm text-ink-gray-8 hover:underline"
                  >{{ f.file_name }}</a
                >
                <span class="shrink-0 font-mono text-xs text-ink-gray-5">{{
                  fileSize(f.file_size)
                }}</span>
                <a
                  :href="downloadHref(f.file_url)"
                  :download="f.file_name"
                  class="grid size-6 place-items-center rounded-md text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
                  :aria-label="__('Download {0}', f.file_name)"
                  :title="__('Download')"
                >
                  <LucideDownload class="size-3.5" aria-hidden="true" />
                </a>
                <button
                  v-if="canRemove(f)"
                  type="button"
                  class="grid size-6 place-items-center rounded-md text-ink-gray-5 hover:bg-surface-gray-2 hover:text-danger"
                  :title="__('Remove')"
                  :aria-label="__('Remove {0}', f.file_name)"
                  @click="removeFile(f.name)"
                >
                  <LucideX class="size-3.5" aria-hidden="true" />
                </button>
              </li>
            </ul>
          </template>
        </div>
        <FormControl
          v-if="form.status === 'Published'"
          v-model="form.published_url"
          :disabled="!canEdit"
          type="url"
          :label="__('Published URL')"
          :placeholder="__('https://instagram.com/p/…')"
          required
        />
        <ErrorMessage :message="error" />
      </form>
    </template>
    <template #actions>
      <div class="flex items-center gap-2">
        <Button
          v-if="!isNew && authStore.isAdmin"
          variant="ghost"
          :label="__('Open full form')"
          :link="`/app/hd-content-post/${post?.name}`"
        />
        <div class="flex-1" />
        <Button
          :label="canEdit ? __('Cancel') : __('Close')"
          @click="open = false"
        />
        <Button
          v-if="canEdit"
          variant="solid"
          type="submit"
          form="content-post-form"
          :loading="saving"
          :label="isNew ? __('Create post') : __('Save changes')"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import {
  Button,
  call,
  Dialog,
  dayjs,
  ErrorMessage,
  createResource,
  FileUploadHandler,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideDownload from "~icons/lucide/download";
import LucideFileText from "~icons/lucide/file-text";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucideX from "~icons/lucide/x";
import LucideClock from "~icons/lucide/clock";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucideMessageSquareWarning from "~icons/lucide/message-square-warning";
import LucideSparkles from "~icons/lucide/sparkles";
import {
  STATUSES,
  htmlToText,
  platformsOf,
  TEAM_ROLES,
  type TeamRole,
  textToHtml,
} from "../constants";
import { useContentOptions } from "../contentOptions";
import AddOptionChip from "./AddOptionChip.vue";
import ChannelIcon from "./ChannelIcon.vue";
import ChipToggle from "./ChipToggle.vue";
import PostTypeIcon from "./PostTypeIcon.vue";
import RoleHoursField from "./RoleHoursField.vue";

interface PostRef {
  name?: string;
  publish_on?: string;
}

const props = defineProps<{ post: PostRef | null }>();
const authStore = useAuthStore();
const open = defineModel<boolean>("open", { default: false });
const emit = defineEmits<{ (e: "saved"): void }>();

const EMPTY = {
  title: "",
  customer: "",
  campaign: "",
  special_day: "",
  channel: "Instagram",
  format: "Post",
  status: "Idea",
  publish_on: "",
  caption: "",
  hashtags: "",
  brief: "",
  published_url: "",
  // each role's estimated hours; empty leaves the task's estimate to AI
  writer_hours: null as number | string | null,
  designer_hours: null as number | string | null,
  video_editor_hours: null as number | string | null,
  marketer_hours: null as number | string | null,
};

const form = reactive({ ...EMPTY });
// everyone on each role, the main person first; saved as the role's field plus More People
const emptyTeam = (): Record<TeamRole, string[]> => ({
  writer: [],
  designer: [],
  video_editor: [],
  marketer: [],
});
const team = reactive(emptyTeam());
// every platform the post goes out on; the first is saved as its channel
const platforms = ref<string[]>([EMPTY.channel]);
const { platforms: platformOptions, postTypes } = useContentOptions();

function addPlatform(channel: string) {
  if (!platforms.value.includes(channel))
    platforms.value = [...platforms.value, channel];
}

function togglePlatform(channel: string) {
  platforms.value = platforms.value.includes(channel)
    ? platforms.value.filter((c) => c !== channel)
    : [...platforms.value, channel];
}
// read-only approval state from the server, never sent back on save
const approval = reactive({
  client_feedback: "",
  client_approval_ref: "",
  sent_for_approval_on: "",
  // cleared each time the post goes back to the client, so set means this round
  head_feedback: "",
});
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const isNew = computed(() => !props.post?.name);
// DM Coordinators, managers and System Managers; others view and attach files
const canEdit = computed(() => authStore.canEditContent);

// datetime-local wants "YYYY-MM-DDTHH:mm"; Frappe stores "YYYY-MM-DD HH:mm:ss"
const toInput = (v?: string) => (v ? dayjs(v).format("YYYY-MM-DDTHH:mm") : "");
const toServer = (v: string) =>
  v ? dayjs(v).format("YYYY-MM-DD HH:mm:ss") : null;

watch(open, async (isOpen) => {
  if (!isOpen) return;
  error.value = "";
  Object.assign(form, EMPTY, { publish_on: toInput(props.post?.publish_on) });
  Object.assign(team, emptyTeam());
  platforms.value = [EMPTY.channel];
  Object.assign(approval, {
    client_feedback: "",
    client_approval_ref: "",
    sent_for_approval_on: "",
    head_feedback: "",
  });
  aiBrief.value = "";
  aiError.value = "";
  undoAi.value = null;
  if (isNew.value) return;
  loading.value = true;
  try {
    const doc = await call("frappe.client.get", {
      doctype: "HD Content Post",
      name: props.post!.name,
    });
    for (const key of Object.keys(EMPTY)) form[key] = doc[key] ?? "";
    // 0 hours shows as an empty box, the same as never estimated
    for (const role of TEAM_ROLES)
      form[`${role.field}_hours`] = doc[`${role.field}_hours`] || null;
    for (const role of TEAM_ROLES)
      team[role.field] = [
        doc[role.field],
        ...(doc.extra_team || [])
          .filter((r: { role: string }) => r.role === role.field)
          .map((r: { user: string }) => r.user),
      ].filter(Boolean);
    platforms.value = platformsOf(doc);
    form.publish_on = toInput(doc.publish_on);
    // Text Editor stores HTML; the dialog edits plain text
    form.caption = htmlToText(doc.caption);
    for (const key of Object.keys(approval)) approval[key] = doc[key] ?? "";
  } finally {
    loading.value = false;
  }
});

// --- images ---

const IMAGE = /\.(png|jpe?g|gif|webp)$/i;
// designs, videos, documents and source files; the client portal shows the images
const ACCEPT =
  "image/*,video/*,application/pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.zip,.psd,.ai,.svg";

const attachments = createResource({
  url: "frappe.client.get_list",
  makeParams: () => ({
    doctype: "File",
    filters: {
      attached_to_doctype: "HD Content Post",
      attached_to_name: props.post?.name,
      is_folder: 0,
    },
    fields: ["name", "file_name", "file_url", "file_size", "owner"],
    order_by: "creation asc",
  }),
});
const imageFiles = computed(() =>
  (attachments.data ?? []).filter((f: any) => IMAGE.test(f.file_name || ""))
);
const otherFiles = computed(() =>
  (attachments.data ?? []).filter((f: any) => !IMAGE.test(f.file_name || ""))
);

const fileInput = ref<HTMLInputElement | null>(null);
const uploading = ref<{ done: number; total: number } | null>(null);
const dragging = ref(false);

function onPick(e: Event) {
  const input = e.target as HTMLInputElement;
  uploadFiles([...(input.files ?? [])]);
  input.value = "";
}

function onDrop(e: DragEvent) {
  dragging.value = false;
  if (isNew.value) return;
  uploadFiles([...(e.dataTransfer?.files ?? [])]);
}

// one at a time: a failed file is reported by name and the rest still upload
async function uploadFiles(files: File[]) {
  if (!files.length || !props.post?.name) return;
  uploading.value = { done: 0, total: files.length };
  const failed: string[] = [];
  for (const file of files) {
    try {
      await new FileUploadHandler().upload(file, {
        doctype: "HD Content Post",
        docname: props.post.name,
        private: true,
      });
    } catch {
      failed.push(file.name);
    }
    uploading.value.done++;
  }
  uploading.value = null;
  attachments.reload();
  const added = files.length - failed.length;
  if (added) {
    toast.success(
      added === 1 ? __("1 file added") : __("{0} files added", String(added))
    );
  }
  if (failed.length) {
    toast.error(__("Couldn't upload {0}", failed.join(", ")));
  }
}

// Files kept in S3 open through a signed link on another host, where browsers
// ignore the download attribute; ask the server for a "save" link instead
function downloadHref(url: string) {
  return url.includes("helpdesk.storage.s3.download")
    ? `${url}&download=1`
    : url;
}

// Frappe zips them and checks read access on every file
function downloadAll() {
  const names = (attachments.data ?? []).map((f: { name: string }) => f.name);
  const params = new URLSearchParams({ files: JSON.stringify(names) });
  window.open(`/api/method/frappe.core.api.file.zip_files?${params}`, "_blank");
}

function fileSize(bytes?: number) {
  if (!bytes) return "";
  if (bytes < 1024 * 1024) return `${Math.max(Math.round(bytes / 1024), 1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

watch(open, (isOpen) => {
  if (isOpen && !isNew.value) attachments.reload();
});

// people who only attach files remove just the ones they added (the server checks too)
function canRemove(file: { owner?: string }) {
  return canEdit.value || file.owner === authStore.userId;
}

async function removeFile(name: string) {
  try {
    await call("frappe.client.delete", { doctype: "File", name });
    attachments.reload();
  } catch (e: any) {
    toast.error(e?.messages?.[0] || __("Couldn't remove the file"));
  }
}

// --- AI drafting ---

const aiBrief = ref("");
const drafting = ref(false);
const aiError = ref("");
const undoAi = ref<{ caption: string; hashtags: string } | null>(null);

async function draftWithAi() {
  aiError.value = "";
  if (!form.title.trim() && !aiBrief.value.trim() && !form.caption.trim()) {
    aiError.value = __(
      "Add the copy or a short brief so the AI knows what to write about."
    );
    return;
  }
  drafting.value = true;
  try {
    const result = await call("helpdesk.api.content.draft_caption", {
      title: form.title,
      channel: form.channel,
      format: form.format,
      customer: form.customer || null,
      campaign: form.campaign || null,
      brief: aiBrief.value,
      current_caption: form.caption,
    });
    undoAi.value = { caption: form.caption, hashtags: form.hashtags };
    form.caption = result.caption;
    if (result.hashtags) form.hashtags = result.hashtags;
  } catch (e: any) {
    aiError.value = e?.messages?.[0] || __("AI drafting failed. Try again.");
  } finally {
    drafting.value = false;
  }
}

function revertAi() {
  if (!undoAi.value) return;
  Object.assign(form, undoAi.value);
  undoAi.value = null;
}

// --- client approval state ---

const approvalNote = computed(() => {
  if (isNew.value) return null;
  if (form.status === "Changes Requested" && approval.head_feedback) {
    return {
      icon: LucideMessageSquareWarning,
      tone: "bg-warning-soft text-warning",
      title: __("The Digital Marketing Head asked for changes"),
      body: approval.head_feedback,
    };
  }
  if (form.status === "Head Review") {
    return {
      icon: LucideClock,
      tone: "bg-info-soft text-info",
      title: __("Client approved · waiting for the Digital Marketing Head"),
      body: authStore.isDmHead
        ? __("Approve it or send it back from the post's card on the board.")
        : __("Only the Digital Marketing Head can approve it or send it back."),
    };
  }
  if (form.status === "Changes Requested" && approval.client_feedback) {
    return {
      icon: LucideMessageSquareWarning,
      tone: "bg-warning-soft text-warning",
      title: __("Client asked for changes"),
      body: approval.client_feedback,
    };
  }
  if (form.status === "Client Review" && approval.client_approval_ref) {
    return {
      icon: LucideClock,
      tone: "bg-info-soft text-info",
      title: __("Waiting for the client's approval in their ERP"),
      body: approval.sent_for_approval_on
        ? __("Sent {0}", dayjs(approval.sent_for_approval_on).fromNow())
        : "",
    };
  }
  if (form.status === "Client Review") {
    return {
      icon: LucideClock,
      tone: "bg-surface-gray-2 text-ink-gray-7",
      title: __(
        "Goes to the client's ERP within 5 minutes if they're connected"
      ),
      body: __("Otherwise, share it with them for approval yourself."),
    };
  }
  if (form.status === "Approved" && approval.client_approval_ref) {
    return {
      icon: LucideCircleCheck,
      tone: "bg-success-soft text-success",
      title: __("Approved by the client"),
      body: "",
    };
  }
  if (!canEdit.value)
    return {
      icon: LucidePaperclip,
      tone: "bg-surface-gray-2 text-ink-gray-7",
      title: __("You can view this entry and add files to it"),
      body: __("Only a DM Coordinator can change the entry itself."),
    };
  return null;
});

async function save() {
  error.value = "";
  if (!canEdit.value) return;
  if (!form.customer) {
    error.value = __("Select a customer for this post");
    return;
  }
  if (!platforms.value.length) {
    error.value = __("Pick at least one platform");
    return;
  }
  if (!form.publish_on && form.status !== "Cancelled") {
    error.value = __("Set the posting date and time");
    return;
  }
  saving.value = true;
  const values = {
    ...form,
    campaign: form.campaign.trim(),
    special_day: form.special_day.trim(),
    channel: platforms.value[0],
    platforms: platforms.value.join(", "),
    publish_on: toServer(form.publish_on),
    caption: textToHtml(form.caption),
    ...Object.fromEntries(
      TEAM_ROLES.map((r) => [r.field, team[r.field][0] || ""])
    ),
    extra_team: TEAM_ROLES.flatMap((r) =>
      team[r.field].slice(1).map((user) => ({ role: r.field, user }))
    ),
  };
  try {
    if (isNew.value) {
      await call("frappe.client.insert", {
        doc: { doctype: "HD Content Post", ...values },
      });
      toast.success(__("Post created"));
    } else {
      await call("frappe.client.set_value", {
        doctype: "HD Content Post",
        name: props.post!.name,
        fieldname: values,
      });
      toast.success(__("Post saved"));
    }
    open.value = false;
    emit("saved");
  } catch (e: any) {
    error.value =
      e?.messages?.[0] || e?.message || __("Couldn't save the post");
  } finally {
    saving.value = false;
  }
}
</script>
