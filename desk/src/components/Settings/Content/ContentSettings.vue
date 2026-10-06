<template>
  <SettingsLayoutBase
    :description="
      __('Missed post alerts and the client portal for the Content Calendar.')
    "
  >
    <template #title>
      <div class="flex items-center gap-2">
        <h1 class="text-lg-semibold text-ink-gray-8">{{ __("Content") }}</h1>
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
        <section>
          <h2 class="text-base-semibold text-ink-gray-9">
            {{ __("Missed post alerts") }}
          </h2>
          <SettingRow
            :label="__('Email when a post is missed')"
            :description="
              __(
                'Checked every hour. A post is missed when its publish time has passed and it is not Published or Cancelled.'
              )
            "
          >
            <Switch v-model="form.enable_missed_post_alerts" />
          </SettingRow>
          <template v-if="form.enable_missed_post_alerts">
            <SettingRow
              :label="__('Grace period')"
              :description="
                __('Minutes to wait after the publish time before alerting.')
              "
            >
              <FormControl
                v-model="form.grace_period_minutes"
                type="number"
                class="w-24"
                min="0"
                :aria-label="__('Grace period in minutes')"
              />
            </SettingRow>
            <SettingRow
              :label="
                __(
                  'Notify the post\'s writer, designer, marketer and video editor'
                )
              "
              :description="__('Along with the people below.')"
            >
              <Switch v-model="form.notify_post_team" />
            </SettingRow>

            <div class="mt-6 flex flex-col gap-2">
              <span class="text-base-medium text-ink-gray-8">{{
                __("Always notify")
              }}</span>
              <div class="flex flex-wrap items-center gap-2">
                <span
                  v-for="user in form.alert_recipients"
                  :key="user"
                  class="inline-flex h-7 items-center gap-1 rounded-full bg-surface-gray-2 ps-2.5 pe-1 text-sm text-ink-gray-8"
                >
                  <span class="font-mono text-xs">{{ user }}</span>
                  <button
                    type="button"
                    class="grid size-5 place-items-center rounded-full text-ink-gray-5 hover:bg-surface-gray-4 hover:text-ink-gray-8"
                    :aria-label="__('Remove {0}', user)"
                    @click="removeRecipient(user)"
                  >
                    <LucideX class="size-3.5" aria-hidden="true" />
                  </button>
                </span>
                <Link
                  v-model="newRecipient"
                  class="w-56"
                  doctype="User"
                  :filters="{ enabled: 1, user_type: 'System User' }"
                  :placeholder="__('Add a person')"
                />
              </div>
            </div>
            <FormControl
              v-model="form.alert_emails"
              class="mt-4"
              type="textarea"
              :rows="2"
              :label="__('Also email')"
              :placeholder="
                __('ops@example.com, one per line or comma separated')
              "
            />

            <TemplateFields
              class="mt-6"
              :title="__('Missed post email')"
              :defaults="defaults.data?.missed_post"
              v-model:subject="form.missed_post_subject"
              v-model:message="form.missed_post_message"
            />
            <p
              v-if="settings.data?.last_alert_run_on"
              class="mt-4 text-p-sm text-ink-gray-5"
            >
              {{
                __(
                  "Last checked {0}, {1} alerts sent",
                  dayjs(settings.data.last_alert_run_on).fromNow(),
                  String(settings.data.last_alerts_sent || 0)
                )
              }}
            </p>
          </template>
        </section>

        <hr class="my-8" />

        <section>
          <h2 class="text-base-semibold text-ink-gray-9">
            {{ __("Tasks from assignments") }}
          </h2>
          <SettingRow
            :label="__('Create a task when someone is assigned')"
            :description="
              __(
                'Writer, designer, digital marketer and video editor each get an ERPNext Task, due on the post\'s date. Unassigning or cancelling the post cancels it.'
              )
            "
          >
            <Switch v-model="form.create_tasks_on_assign" />
          </SettingRow>
          <div
            v-if="form.create_tasks_on_assign"
            class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
          >
            <FormControl
              v-model="form.writer_hours"
              type="number"
              min="0"
              step="0.5"
              :label="__('Writer hours')"
            />
            <FormControl
              v-model="form.designer_hours"
              type="number"
              min="0"
              step="0.5"
              :label="__('Designer hours')"
            />
            <FormControl
              v-model="form.marketer_hours"
              type="number"
              min="0"
              step="0.5"
              :label="__('Digital marketer hours')"
            />
            <FormControl
              v-model="form.video_editor_hours"
              type="number"
              min="0"
              step="0.5"
              :label="__('Video editor hours')"
            />
          </div>
        </section>

        <hr class="my-8" />

        <section>
          <h2 class="text-base-semibold text-ink-gray-9">
            {{ __("Client portal") }}
          </h2>
          <SettingRow
            :label="__('Enable the client portal')"
            :description="
              __(
                'Clients sign in with their contact email and a one-time code to review, approve and comment on posts in Client Review.'
              )
            "
          >
            <Switch v-model="form.enable_client_portal" />
          </SettingRow>
          <template v-if="form.enable_client_portal">
            <div class="mt-4 flex items-center gap-2 text-p-sm text-ink-gray-6">
              {{ __("Portal link") }}
              <a
                class="font-mono text-ink-gray-8 underline"
                :href="portalUrl"
                target="_blank"
                rel="noopener"
                >{{ portalUrl }}</a
              >
            </div>
            <TemplateFields
              class="mt-6"
              :title="__('Sign-in code email')"
              :defaults="defaults.data?.portal_code"
              v-model:subject="form.portal_code_subject"
              v-model:message="form.portal_code_message"
            />
          </template>
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
  dayjs,
  FormControl,
  LoadingIndicator,
  Switch,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideX from "~icons/lucide/x";
import { disableSettingModalOutsideClick } from "../settingsModal";
import SettingRow from "./SettingRow.vue";
import TemplateFields from "./TemplateFields.vue";

interface ContentSettingsForm {
  enable_missed_post_alerts: boolean;
  grace_period_minutes: number;
  notify_post_team: boolean;
  alert_recipients: string[];
  alert_emails: string;
  missed_post_subject: string;
  missed_post_message: string;
  enable_client_portal: boolean;
  portal_code_subject: string;
  portal_code_message: string;
  create_tasks_on_assign: boolean;
  writer_hours: number;
  designer_hours: number;
  marketer_hours: number;
  video_editor_hours: number;
}

const DOCTYPE = "HD Content Settings";
const form = ref<ContentSettingsForm | null>(null);
const initial = ref("");
const newRecipient = ref("");
const portalUrl = `${window.location.origin}/content-portal`;

const settings = createResource({
  url: "frappe.client.get",
  params: { doctype: DOCTYPE, name: DOCTYPE },
  auto: true,
  onSuccess(doc) {
    form.value = {
      enable_missed_post_alerts: Boolean(doc.enable_missed_post_alerts),
      grace_period_minutes: doc.grace_period_minutes ?? 0,
      notify_post_team: Boolean(doc.notify_post_team),
      alert_recipients: (doc.alert_recipients || []).map(
        (row: { user: string }) => row.user
      ),
      alert_emails: doc.alert_emails || "",
      missed_post_subject: doc.missed_post_subject || "",
      missed_post_message: doc.missed_post_message || "",
      enable_client_portal: Boolean(doc.enable_client_portal),
      portal_code_subject: doc.portal_code_subject || "",
      portal_code_message: doc.portal_code_message || "",
      create_tasks_on_assign: Boolean(doc.create_tasks_on_assign),
      writer_hours: doc.writer_hours ?? 0,
      designer_hours: doc.designer_hours ?? 0,
      marketer_hours: doc.marketer_hours ?? 0,
      video_editor_hours: doc.video_editor_hours ?? 0,
    };
    initial.value = JSON.stringify(form.value);
  },
});

const defaults = createResource({
  url: "helpdesk.helpdesk.doctype.hd_content_settings.hd_content_settings.get_template_defaults",
  auto: true,
});

const isDirty = computed(
  () => !!form.value && JSON.stringify(form.value) !== initial.value
);
watch(isDirty, (dirty) => (disableSettingModalOutsideClick.value = dirty));

watch(newRecipient, (user) => {
  if (!user || !form.value) return;
  if (!form.value.alert_recipients.includes(user)) {
    form.value.alert_recipients.push(user);
  }
  newRecipient.value = "";
});

function removeRecipient(user: string) {
  form.value!.alert_recipients = form.value!.alert_recipients.filter(
    (u) => u !== user
  );
}

const save = createResource({
  url: "frappe.client.set_value",
  makeParams() {
    const f = form.value!;
    return {
      doctype: DOCTYPE,
      name: DOCTYPE,
      fieldname: {
        ...f,
        enable_missed_post_alerts: f.enable_missed_post_alerts ? 1 : 0,
        notify_post_team: f.notify_post_team ? 1 : 0,
        enable_client_portal: f.enable_client_portal ? 1 : 0,
        grace_period_minutes: Number(f.grace_period_minutes) || 0,
        create_tasks_on_assign: f.create_tasks_on_assign ? 1 : 0,
        writer_hours: Number(f.writer_hours) || 0,
        designer_hours: Number(f.designer_hours) || 0,
        marketer_hours: Number(f.marketer_hours) || 0,
        video_editor_hours: Number(f.video_editor_hours) || 0,
        alert_recipients: f.alert_recipients.map((user) => ({ user })),
      },
    };
  },
  onSuccess() {
    initial.value = JSON.stringify(form.value);
    toast.success(__("Content settings saved"));
  },
  onError(e: { messages?: string[] }) {
    toast.error(e.messages?.[0] || __("Couldn't save content settings"));
  },
});
</script>
