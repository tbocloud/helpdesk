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
        <FormControl
          v-model="form.title"
          :label="__('Title')"
          :placeholder="__('e.g. Diwali offer carousel')"
          required
        />
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Link
            v-model="form.customer"
            doctype="HD Customer"
            :label="__('Customer') + ' *'"
            :placeholder="__('Select customer')"
          />
          <Link
            v-model="form.campaign"
            doctype="HD Content Campaign"
            :filters="form.customer ? { customer: form.customer } : undefined"
            :label="__('Campaign (optional)')"
            :placeholder="__('Select campaign')"
          />
          <fieldset class="flex flex-col gap-1.5 sm:col-span-2">
            <legend class="mb-1.5 text-xs text-ink-gray-5">
              {{ __("Platforms") }} ·
              <span>{{ __("this one post goes out on each") }}</span>
            </legend>
            <div class="flex flex-wrap gap-1.5">
              <ChipToggle
                v-for="channel in CHANNELS"
                :key="channel"
                :label="channel"
                :pressed="platforms.includes(channel)"
                @toggle="togglePlatform(channel)"
              />
            </div>
          </fieldset>
          <FormControl
            v-model="form.format"
            type="select"
            :label="__('Format')"
            :options="FORMATS"
          />
          <FormControl
            v-model="form.status"
            type="select"
            :label="__('Status')"
            :options="STATUSES"
          />
          <FormControl
            v-model="form.publish_on"
            type="datetime-local"
            :label="__('Publish on')"
            :description="
              form.status === 'Idea' ? __('Optional while it is an idea') : ''
            "
          />
          <Link
            v-model="form.writer"
            doctype="User"
            :label="__('Writer')"
            :placeholder="__('Assign writer')"
          />
          <Link
            v-model="form.designer"
            doctype="User"
            :label="__('Designer')"
            :placeholder="__('Assign designer')"
          />
          <Link
            v-model="form.marketer"
            doctype="User"
            :label="__('Digital marketer')"
            :placeholder="__('Assign marketer')"
          />
        </div>
        <div class="flex flex-col gap-1.5">
          <div class="flex items-center justify-between gap-2">
            <label for="post-caption" class="text-xs text-ink-gray-5">{{
              __("Caption")
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
          v-model="form.hashtags"
          :label="__('Hashtags')"
          :placeholder="__('#diwali #offers')"
        />
        <FormControl
          v-model="form.brief"
          type="textarea"
          :rows="2"
          :label="__('Brief for the creative team')"
          :placeholder="__('What should the design or video look like?')"
          :description="__('Internal only. The client never sees this.')"
        />
        <div class="flex flex-col gap-1.5">
          <div class="flex items-center justify-between">
            <span class="text-xs text-ink-gray-5">{{ __("Images") }}</span>
            <FileUploader
              v-if="!isNew"
              :file-types="['image/*']"
              :upload-args="{
                doctype: 'HD Content Post',
                docname: post?.name,
                private: true,
              }"
              @success="images.reload()"
            >
              <template #default="{ openFileSelector, uploading }">
                <Button
                  size="sm"
                  :loading="uploading"
                  :label="__('Add image')"
                  @click="openFileSelector()"
                >
                  <template #prefix
                    ><LucideImagePlus class="size-4" aria-hidden="true"
                  /></template>
                </Button>
              </template>
            </FileUploader>
          </div>
          <p v-if="isNew" class="text-p-sm text-ink-gray-5">
            {{ __("Create the post first, then add its designs here.") }}
          </p>
          <p v-else-if="!images.data?.length" class="text-p-sm text-ink-gray-5">
            {{
              __(
                "No images yet. They're sent to the client with the approval request."
              )
            }}
          </p>
          <ul v-else class="grid grid-cols-3 gap-2 sm:grid-cols-4" role="list">
            <li
              v-for="img in images.data"
              :key="img.name"
              class="group relative aspect-square overflow-hidden rounded-lg border border-outline-gray-2"
            >
              <img
                :src="img.file_url"
                :alt="img.file_name"
                class="size-full object-cover"
              />
              <button
                type="button"
                class="absolute right-1 top-1 grid size-6 place-items-center rounded-md bg-surface-base/90 text-ink-gray-7 opacity-0 shadow-sm transition group-hover:opacity-100 focus-visible:opacity-100"
                :aria-label="__('Remove {0}', img.file_name)"
                @click="removeImage(img.name)"
              >
                <LucideX class="size-3.5" aria-hidden="true" />
              </button>
            </li>
          </ul>
        </div>
        <FormControl
          v-if="form.status === 'Published'"
          v-model="form.published_url"
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
        <Button :label="__('Cancel')" @click="open = false" />
        <Button
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
  FileUploader,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideImagePlus from "~icons/lucide/image-plus";
import LucideX from "~icons/lucide/x";
import LucideClock from "~icons/lucide/clock";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucideMessageSquareWarning from "~icons/lucide/message-square-warning";
import LucideSparkles from "~icons/lucide/sparkles";
import {
  CHANNELS,
  FORMATS,
  STATUSES,
  htmlToText,
  platformsOf,
  textToHtml,
} from "../constants";
import ChipToggle from "./ChipToggle.vue";

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
  channel: "Instagram",
  format: "Post",
  status: "Idea",
  publish_on: "",
  writer: "",
  designer: "",
  marketer: "",
  caption: "",
  hashtags: "",
  brief: "",
  published_url: "",
};

const form = reactive({ ...EMPTY });
// every platform the post goes out on; the first is saved as its channel
const platforms = ref<string[]>([EMPTY.channel]);

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
});
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const isNew = computed(() => !props.post?.name);

// datetime-local wants "YYYY-MM-DDTHH:mm"; Frappe stores "YYYY-MM-DD HH:mm:ss"
const toInput = (v?: string) => (v ? dayjs(v).format("YYYY-MM-DDTHH:mm") : "");
const toServer = (v: string) =>
  v ? dayjs(v).format("YYYY-MM-DD HH:mm:ss") : null;

watch(open, async (isOpen) => {
  if (!isOpen) return;
  error.value = "";
  Object.assign(form, EMPTY, { publish_on: toInput(props.post?.publish_on) });
  platforms.value = [EMPTY.channel];
  Object.assign(approval, {
    client_feedback: "",
    client_approval_ref: "",
    sent_for_approval_on: "",
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

const images = createResource({
  url: "frappe.client.get_list",
  makeParams: () => ({
    doctype: "File",
    filters: {
      attached_to_doctype: "HD Content Post",
      attached_to_name: props.post?.name,
      is_folder: 0,
    },
    fields: ["name", "file_name", "file_url"],
    order_by: "creation asc",
  }),
  transform: (files: any[]) =>
    (files ?? []).filter((f) =>
      /\.(png|jpe?g|gif|webp)$/i.test(f.file_name || "")
    ),
});

watch(open, (isOpen) => {
  if (isOpen && !isNew.value) images.reload();
});

async function removeImage(name: string) {
  try {
    await call("frappe.client.delete", { doctype: "File", name });
    images.reload();
  } catch (e: any) {
    toast.error(e?.messages?.[0] || __("Couldn't remove the image"));
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
      "Add a title or a short brief so the AI knows what to write about."
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
  return null;
});

async function save() {
  error.value = "";
  // The server fills customer from the campaign, so only one of them is needed
  if (!form.customer && !form.campaign) {
    error.value = __("Select a customer for this post");
    return;
  }
  saving.value = true;
  if (!platforms.value.length) {
    error.value = __("Pick at least one platform");
    return;
  }
  const values = {
    ...form,
    channel: platforms.value[0],
    platforms: platforms.value.join(", "),
    publish_on: toServer(form.publish_on),
    caption: textToHtml(form.caption),
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
