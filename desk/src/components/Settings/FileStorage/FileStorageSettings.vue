<template>
  <SettingsLayoutBase
    :description="
      __(
        'Keep attachments in your own S3 bucket instead of on this server. People still open them from helpdesk, with the same access rules.'
      )
    "
  >
    <template #title>
      <div class="flex items-center gap-2">
        <h1 class="text-lg-semibold text-ink-gray-8">
          {{ __("File storage") }}
        </h1>
        <UnsavedBadge :show="isDirty" />
      </div>
    </template>
    <template #header-actions>
      <Transition name="fade">
        <Button
          v-if="isDirty"
          variant="solid"
          :label="__('Save')"
          :loading="save.loading"
          @click="save.submit()"
        />
      </Transition>
    </template>
    <template #content>
      <div
        v-if="!form"
        class="flex items-center justify-center absolute inset-x-0 top-5.5 bottom-0"
      >
        <LoadingIndicator class="w-4" />
      </div>
      <div v-else class="flex flex-col">
        <SettingRow
          :label="__('Store files in S3')"
          :description="
            __(
              'New attachments of the document types below go to the bucket. Turn it on after the connection test passes.'
            )
          "
        >
          <Switch v-model="form.enabled" />
        </SettingRow>

        <hr class="my-8" />

        <section class="flex flex-col gap-4">
          <h2 class="text-base-semibold text-ink-gray-9">{{ __("Bucket") }}</h2>
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormControl
              v-model="form.bucket"
              :label="__('Bucket name')"
              placeholder="tbo-helpdesk-files"
            />
            <FormControl
              v-model="form.region"
              :label="__('Region')"
              placeholder="ap-south-1"
            />
            <FormControl
              v-model="form.access_key_id"
              :label="__('Access key ID')"
              placeholder="AKIA…"
              autocomplete="off"
            />
            <FormControl
              v-model="form.secret_access_key"
              type="password"
              :label="__('Secret access key')"
              :placeholder="
                hasSecret ? __('Saved. Type a new one to replace it.') : ''
              "
              autocomplete="new-password"
            />
            <FormControl
              v-model="form.key_prefix"
              :label="__('Folder prefix')"
              :placeholder="siteName"
              :description="__('Files go under this folder in the bucket.')"
            />
            <FormControl
              v-model="form.endpoint_url"
              :label="__('Endpoint URL (optional)')"
              placeholder="https://s3.example.com"
              :description="
                __('Leave empty for AWS. Needed for MinIO, Wasabi and similar.')
              "
            />
          </div>
          <div class="flex flex-wrap items-center gap-3">
            <Button
              :label="__('Test connection')"
              :loading="test.loading"
              :disabled="isDirty"
              :tooltip="isDirty ? __('Save first') : ''"
              @click="test.submit()"
            >
              <template #prefix
                ><LucidePlugZap class="size-4" aria-hidden="true"
              /></template>
            </Button>
            <span
              v-if="lastTest"
              class="inline-flex items-center gap-1.5 text-p-sm"
              :class="lastTest.ok ? 'text-success' : 'text-danger'"
              role="status"
            >
              <component
                :is="lastTest.ok ? LucideCircleCheck : LucideCircleAlert"
                class="size-4 shrink-0"
                aria-hidden="true"
              />
              {{ lastTest.message }}
            </span>
          </div>
        </section>

        <hr class="my-8" />

        <section class="flex flex-col gap-4">
          <h2 class="text-base-semibold text-ink-gray-9">
            {{ __("What goes to S3") }}
          </h2>
          <div class="flex flex-col gap-2">
            <span class="text-base-medium text-ink-gray-8">{{
              __("Attachments of")
            }}</span>
            <div class="flex flex-wrap items-center gap-2">
              <span
                v-for="dt in form.document_types"
                :key="dt"
                class="inline-flex h-7 items-center gap-1 rounded-full bg-surface-gray-2 ps-2.5 pe-1 text-sm text-ink-gray-8"
              >
                {{ dt }}
                <button
                  type="button"
                  class="grid size-5 place-items-center rounded-full text-ink-gray-5 hover:bg-surface-gray-4 hover:text-ink-gray-8"
                  :aria-label="__('Remove {0}', dt)"
                  @click="
                    form.document_types = form.document_types.filter(
                      (d) => d !== dt
                    )
                  "
                >
                  <LucideX class="size-3.5" aria-hidden="true" />
                </button>
              </span>
              <Link
                v-model="newDoctype"
                class="w-56"
                doctype="DocType"
                :filters="{ istable: 0, issingle: 0 }"
                :placeholder="__('Add a document type')"
              />
            </div>
          </div>
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormControl
              v-model="form.link_expiry_seconds"
              type="number"
              min="60"
              :label="__('Download links valid for (seconds)')"
              :description="
                __(
                  'After their access is checked, people get a signed link that stops working after this long.'
                )
              "
            />
          </div>
          <SettingRow
            :label="__('Delete from the bucket when a file is deleted')"
            :description="
              __('Keep this on unless your bucket keeps old versions for you.')
            "
          >
            <Switch v-model="form.delete_from_bucket" />
          </SettingRow>
        </section>

        <hr class="my-8" />

        <section class="flex flex-col gap-3">
          <h2 class="text-base-semibold text-ink-gray-9">
            {{ __("Existing files") }}
          </h2>
          <p v-if="overview.data" class="text-p-sm text-ink-gray-6">
            <span class="font-mono tabular-nums">{{
              overview.data.in_bucket
            }}</span>
            {{ __("in the bucket") }} ·
            <span class="font-mono tabular-nums">{{
              overview.data.local
            }}</span>
            {{ __("still on this server") }}
          </p>
          <div>
            <Button
              :label="__('Move existing files to S3')"
              :disabled="!settings.data?.enabled || !overview.data?.local"
              :loading="move.loading"
              @click="move.submit()"
            >
              <template #prefix
                ><LucideCloudUpload class="size-4" aria-hidden="true"
              /></template>
            </Button>
          </div>
          <p class="text-p-sm text-ink-gray-5">
            {{
              __(
                "Runs in the background. Files that fail to upload stay on this server and are listed in the Error Log."
              )
            }}
          </p>
        </section>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import UnsavedBadge from "@/components/UnsavedBadge.vue";
import { __ } from "@/translation";
import {
  Button,
  createResource,
  FormControl,
  LoadingIndicator,
  Switch,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCloudUpload from "~icons/lucide/cloud-upload";
import LucidePlugZap from "~icons/lucide/plug-zap";
import LucideX from "~icons/lucide/x";
import SettingRow from "../Content/SettingRow.vue";
import { disableSettingModalOutsideClick } from "../settingsModal";

interface StorageForm {
  enabled: boolean;
  bucket: string;
  region: string;
  endpoint_url: string;
  access_key_id: string;
  // empty means "keep the saved one"
  secret_access_key: string;
  key_prefix: string;
  document_types: string[];
  link_expiry_seconds: number;
  delete_from_bucket: boolean;
}

const DOCTYPE = "HD File Storage Settings";
const siteName = window.location.hostname;
const form = ref<StorageForm | null>(null);
const initial = ref("");
const hasSecret = ref(false);
const newDoctype = ref("");
const lastTest = ref<{ ok: boolean; message: string } | null>(null);

const settings = createResource({
  url: "frappe.client.get",
  params: { doctype: DOCTYPE, name: DOCTYPE },
  auto: true,
  onSuccess(doc) {
    hasSecret.value = Boolean(doc.secret_access_key);
    form.value = {
      enabled: Boolean(doc.enabled),
      bucket: doc.bucket || "",
      region: doc.region || "",
      endpoint_url: doc.endpoint_url || "",
      access_key_id: doc.access_key_id || "",
      secret_access_key: "",
      key_prefix: doc.key_prefix || "",
      document_types: (doc.document_types || []).map(
        (r: { document_type: string }) => r.document_type
      ),
      link_expiry_seconds: doc.link_expiry_seconds || 600,
      delete_from_bucket: Boolean(doc.delete_from_bucket),
    };
    initial.value = JSON.stringify(form.value);
    if (doc.last_test_result) {
      lastTest.value = {
        ok: Boolean(doc.last_test_ok),
        message: doc.last_test_result,
      };
    }
  },
});

const overview = createResource({
  url: "helpdesk.storage.s3.get_overview",
  auto: true,
});

const isDirty = computed(
  () => !!form.value && JSON.stringify(form.value) !== initial.value
);
watch(isDirty, (dirty) => (disableSettingModalOutsideClick.value = dirty));

watch(newDoctype, (dt) => {
  if (!dt || !form.value) return;
  if (!form.value.document_types.includes(dt))
    form.value.document_types.push(dt);
  newDoctype.value = "";
});

const save = createResource({
  url: "frappe.client.set_value",
  makeParams() {
    const f = form.value!;
    const fieldname: Record<string, unknown> = {
      ...f,
      enabled: f.enabled ? 1 : 0,
      delete_from_bucket: f.delete_from_bucket ? 1 : 0,
      link_expiry_seconds: Number(f.link_expiry_seconds) || 600,
      document_types: f.document_types.map((document_type) => ({
        document_type,
      })),
    };
    // never send the saved secret back; only a newly typed one
    if (!f.secret_access_key) delete fieldname.secret_access_key;
    return { doctype: DOCTYPE, name: DOCTYPE, fieldname };
  },
  onSuccess() {
    toast.success(__("File storage saved"));
    settings.reload();
    overview.reload();
  },
  onError(e: { messages?: string[] }) {
    toast.error(e.messages?.[0] || __("Couldn't save file storage"));
  },
});

const test = createResource({
  url: "helpdesk.storage.s3.test_connection",
  onSuccess(result: { ok: boolean; message: string }) {
    lastTest.value = result;
  },
  onError(e: { messages?: string[] }) {
    lastTest.value = {
      ok: false,
      message: e.messages?.[0] || __("Couldn't test the connection"),
    };
  },
});

const move = createResource({
  url: "helpdesk.storage.s3.move_existing_files",
  onSuccess() {
    toast.success(
      __("Moving files in the background. Check back in a few minutes.")
    );
  },
  onError(e: { messages?: string[] }) {
    toast.error(e.messages?.[0] || __("Couldn't start moving files"));
  },
});
</script>
