<template>
  <SettingsLayoutBase
    :title="__('File storage')"
    :description="
      __(
        'Keep attachments in your own S3 bucket instead of on this server. People still open them from helpdesk, with the same access rules.'
      )
    "
    :dirty="isDirty"
    :saving="save.loading"
    :loading="!form && !settings.error"
    :error="settings.error"
    @retry="settings.reload()"
    @save="save.submit()"
  >
    <template #content>
      <div v-if="form">
        <SettingsSection :title="__('Storage')">
          <SettingRow
            v-slot="{ id }"
            :label="__('Store files in S3')"
            :description="
              __(
                'New attachments of the document types below go to the bucket. Turn it on after the connection test passes.'
              )
            "
          >
            <Switch :id="id" v-model="form.enabled" />
          </SettingRow>
        </SettingsSection>

        <SettingsSection :title="__('Bucket')">
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
              :tooltip="isDirty ? __('Save your changes first') : ''"
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
        </SettingsSection>

        <SettingsSection :title="__('What goes to S3')">
          <div class="flex flex-col gap-2">
            <span class="text-base-medium text-ink-gray-8">{{
              __("Attachments of")
            }}</span>
            <ChipListInput
              v-model="form.document_types"
              doctype="DocType"
              :filters="{ istable: 0, issingle: 0 }"
              :placeholder="__('Add a document type')"
            />
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
            v-slot="{ id }"
            :label="__('Keep a copy on this server')"
            :description="
              form.keep_local_copy
                ? __(
                    'Files stay on this server and open from here; the bucket holds a second copy. If the server copy is lost, it is read back from the bucket.'
                  )
                : __(
                    'Files live only in the bucket and are removed from this server after upload.'
                  )
            "
          >
            <Switch :id="id" v-model="form.keep_local_copy" />
          </SettingRow>
          <SettingRow
            v-slot="{ id }"
            :label="__('Delete from the bucket when a file is deleted')"
            :description="
              __('Keep this on unless your bucket keeps old versions for you.')
            "
          >
            <Switch :id="id" v-model="form.delete_from_bucket" />
          </SettingRow>
        </SettingsSection>

        <SettingsSection
          :title="__('Existing files')"
          :description="
            __(
              'Copies them to the bucket in the background. Files that fail to upload stay on this server and are listed in the Error Log.'
            )
          "
        >
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
              :label="__('Copy existing files to S3')"
              :disabled="!settings.data?.enabled || !overview.data?.local"
              :loading="move.loading"
              @click="move.submit()"
            >
              <template #prefix
                ><LucideCloudUpload class="size-4" aria-hidden="true"
              /></template>
            </Button>
          </div>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { __ } from "@/translation";
import { Button, createResource, FormControl, Switch, toast } from "frappe-ui";
import { computed, ref } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCloudUpload from "~icons/lucide/cloud-upload";
import LucidePlugZap from "~icons/lucide/plug-zap";
import ChipListInput from "../ChipListInput.vue";
import SettingRow from "../SettingRow.vue";
import SettingsSection from "../SettingsSection.vue";

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
  keep_local_copy: boolean;
}

const DOCTYPE = "HD File Storage Settings";
const siteName = window.location.hostname;
const form = ref<StorageForm | null>(null);
const initial = ref("");
const hasSecret = ref(false);
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
      keep_local_copy: Boolean(doc.keep_local_copy),
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

const save = createResource({
  url: "frappe.client.set_value",
  makeParams() {
    const f = form.value!;
    const fieldname: Record<string, unknown> = {
      ...f,
      enabled: f.enabled ? 1 : 0,
      delete_from_bucket: f.delete_from_bucket ? 1 : 0,
      keep_local_copy: f.keep_local_copy ? 1 : 0,
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
