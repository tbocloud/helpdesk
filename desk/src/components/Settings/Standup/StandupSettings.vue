<template>
  <SettingsLayoutBase
    :title="__('Stand-up')"
    :description="
      __(
        'The async daily stand-up: drafts filled in from everyone\'s work, one reminder, and each department\'s summary in Teams.'
      )
    "
    :dirty="isDirty"
    :saving="save.loading"
    :loading="!form && !settings.error"
    :error="settings.error"
    @retry="settings.reload()"
    @save="save.submit()"
  >
    <template v-if="form" #header-actions>
      <Switch v-model="form.enabled" :label="__('Enabled')" />
    </template>
    <template #content>
      <div v-if="form">
        <SettingsSection
          :title="__('Times')"
          :description="
            __(
              'Working days only (the weekly off, Saturdays off and business holidays are skipped). 24-hour times, in order.'
            )
          "
        >
          <SettingRow
            v-for="time in TIMES"
            :key="time.field"
            v-slot="{ id }"
            :label="time.label"
            :description="time.description"
          >
            <FormControl
              :id="id"
              v-model="form[time.field]"
              type="text"
              class="w-full sm:w-28"
              :placeholder="time.placeholder"
            />
          </SettingRow>
          <SettingRow
            v-slot="{ id }"
            :label="__('Show hours logged')"
            :description="
              __(
                'Each person\'s hours on the previous working day, as a fact. Never judged and never sent to the AI.'
              )
            "
          >
            <Switch :id="id" v-model="form.include_hours" />
          </SettingRow>
        </SettingsSection>

        <SettingsSection
          :title="__('Departments and channels')"
          :description="
            __(
              'Who is in the stand-up, and the Teams channel each department\'s summary goes to. With none listed, everyone is in and every summary goes to the escalation channel.'
            )
          "
        >
          <p
            v-if="!data?.chat.enabled || !data?.chat.fallback_channel"
            class="flex items-start gap-1.5 text-p-sm text-warning"
          >
            <LucideTriangleAlert
              class="mt-0.5 size-4 shrink-0"
              aria-hidden="true"
            />
            {{
              !data?.chat.enabled
                ? __(
                    "Chat is off, so summaries aren't posted. Turn it on in Chat & Teams."
                  )
                : __(
                    "No escalation channel: departments without their own channel aren't posted."
                  )
            }}
          </p>
          <ul v-if="rows.length" role="list" class="flex flex-col gap-4">
            <li
              v-for="(row, index) in rows"
              :key="row.key"
              class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 p-3"
            >
              <div class="flex items-end gap-2">
                <Link
                  v-model="row.department"
                  class="min-w-0 flex-1"
                  doctype="HD Department"
                  :filters="{ is_active: 1 }"
                  :label="__('Department')"
                  :placeholder="__('Select department')"
                />
                <Button
                  variant="ghost"
                  :aria-label="
                    __('Remove {0}', row.department || __('department'))
                  "
                  @click="rows.splice(index, 1)"
                >
                  <template #icon>
                    <LucideTrash2 class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </div>
              <SecretField
                v-if="data?.chat.platform === 'Microsoft Teams'"
                v-model="row.edit"
                :label="__('Teams channel workflow URL')"
                :description="
                  __(
                    'Teams Workflow template \'Post to a channel when a webhook request is received\'. Empty: the escalation channel.'
                  )
                "
                :status="row.status"
                type="password"
                placeholder="https://…logic.azure.com/…"
                removable
              />
            </li>
          </ul>
          <Button :label="__('Add department')" @click="addRow">
            <template #prefix>
              <LucidePlus class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </SettingsSection>

        <SettingsSection
          :title="__('Team view')"
          :description="
            __(
              'Who sees their teams\' stand-ups with Nudge, the blocker actions and plan against done. Admins always do; everyone else sees their own department\'s summary, as in Teams.'
            )
          "
        >
          <SettingRow
            v-for="flag in TEAM_FLAGS"
            :key="flag.field"
            v-slot="{ id }"
            :label="flag.label"
            :description="flag.description"
          >
            <Switch :id="id" v-model="form[flag.field]" />
          </SettingRow>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { __ } from "@/translation";
import { Button, createResource, FormControl, Switch, toast } from "frappe-ui";
import { computed, ref } from "vue";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import SecretField, {
  type SecretEdit,
  type SecretStatus,
} from "../SecretField.vue";
import { secretValue } from "../secretEdit";
import SettingRow from "../SettingRow.vue";
import SettingsSection from "../SettingsSection.vue";

interface SettingsData {
  settings: Record<string, any>;
  departments: { department: string; channel: SecretStatus }[];
  chat: { enabled: boolean; platform: string; fallback_channel: boolean };
}

interface Row {
  key: number;
  department: string;
  status: SecretStatus;
  edit: SecretEdit;
}

// Check fields come as 0/1 and go back the same way
const CHECKS = [
  "enabled",
  "include_hours",
  "team_view_heads",
  "team_view_leads",
  "team_view_project_managers",
];

const TIMES = [
  {
    field: "open_at",
    label: __("Drafts open"),
    description: __(
      "Everyone's draft is filled in and they are told in the app and in Teams."
    ),
    placeholder: "09:00",
  },
  {
    field: "remind_at",
    label: __("Reminder"),
    description: __("Once, to anyone who hasn't submitted."),
    placeholder: "10:00",
  },
  {
    field: "post_at",
    label: __("Summary posts"),
    description: __("Drafts go out as filled in, marked (auto)."),
    placeholder: "10:30",
  },
];

const TEAM_FLAGS = [
  {
    field: "team_view_heads",
    label: __("Department heads"),
    description: __("For the departments they head."),
  },
  {
    field: "team_view_leads",
    label: __("Project leads and coordinators"),
    description: __(
      "For the departments of the projects they lead or coordinate."
    ),
  },
  {
    field: "team_view_project_managers",
    label: __("Project managers"),
    description: __("For the departments of the projects they manage."),
  },
];

const form = ref<Record<string, any> | null>(null);
const rows = ref<Row[]>([]);
const initial = ref("");
let nextKey = 0;

function load(data: SettingsData) {
  const f = { ...data.settings };
  for (const key of CHECKS) f[key] = Boolean(Number(f[key]));
  form.value = f;
  rows.value = data.departments.map((d) => ({
    key: nextKey++,
    department: d.department,
    status: d.channel,
    edit: { mode: "keep", value: "" },
  }));
  initial.value = snapshot();
}

function snapshot() {
  return JSON.stringify([
    form.value,
    rows.value.map((r) => [r.department, secretValue(r.edit)]),
  ]);
}

const settings = createResource({
  url: "helpdesk.api.standup.get_settings",
  auto: true,
  onSuccess: load,
});
const data = computed(() => settings.data as SettingsData | undefined);
const isDirty = computed(() => !!form.value && snapshot() !== initial.value);

function addRow() {
  rows.value.push({
    key: nextKey++,
    department: "",
    status: { set: false, masked: "" },
    edit: { mode: "replace", value: "" },
  });
}

const save = createResource({
  url: "helpdesk.api.standup.save_settings",
  makeParams() {
    const values: Record<string, any> = { ...form.value };
    for (const key of CHECKS) values[key] = values[key] ? 1 : 0;
    values.departments = rows.value
      .filter((r) => r.department)
      .map((r) => {
        const webhook = secretValue(r.edit);
        return webhook === undefined
          ? { department: r.department }
          : { department: r.department, channel_webhook: webhook };
      });
    return { values };
  },
  onSuccess(saved: SettingsData) {
    settings.setData(saved);
    load(saved);
    toast.success(__("Stand-up settings saved"));
  },
  onError(e: { messages?: string[] }) {
    toast.error(e.messages?.[0] || __("Couldn't save the stand-up settings"));
  },
});
</script>
