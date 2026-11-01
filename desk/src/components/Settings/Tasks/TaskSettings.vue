<template>
  <SettingsLayoutBase
    :title="__('Tasks')"
    :description="
      __(
        'How the AI helps when tasks are created, support hours alerts and who gets the Friday project status report.'
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
        <SettingsSection
          :title="__('AI')"
          :description="
            aiStatus.data?.available === false
              ? aiStatus.data.reason
              : undefined
          "
        >
          <SettingRow
            v-slot="{ id }"
            :label="__('Write descriptions for new tasks with AI')"
            :description="
              __(
                'A task created without a description gets one in the background: the goal, the steps and when it is done. Text someone typed is never replaced.'
              )
            "
          >
            <Switch :id="id" v-model="form.ai_task_descriptions" />
          </SettingRow>
          <SettingRow
            v-slot="{ id }"
            :label="__('AI sets the time for new tasks')"
            :description="
              __(
                'A task created without a due date gets working days and hours from the task, the project type and how long similar tasks took.'
              )
            "
          >
            <Switch :id="id" v-model="form.ai_task_estimates" />
          </SettingRow>
          <SettingRow
            v-if="form.ai_task_estimates"
            v-slot="{ id }"
            :label="__('Longest estimate')"
            :description="__('Working days.')"
          >
            <FormControl
              :id="id"
              v-model="form.max_task_days"
              type="number"
              class="w-24"
              min="1"
              :aria-label="__('Longest estimate in working days')"
            />
          </SettingRow>
        </SettingsSection>
        <SettingsSection
          :title="__('Support hours')"
          :description="
            __(
              'The team is always told when a customer\'s support contract reaches its alert level and when its hours are used up.'
            )
          "
        >
          <SettingRow
            v-slot="{ id }"
            :label="__('Email the customer too')"
            :description="
              __(
                'The customer\'s contacts get the same two emails each period, with the hours used and left.'
              )
            "
          >
            <Switch :id="id" v-model="form.support_hours_email_customer" />
          </SettingRow>
        </SettingsSection>
        <SettingsSection
          :title="__('Project status report')"
          :description="
            __(
              'Every Friday at 17:00 the report goes to these people, in chat or by email. Left empty it goes to the System Managers and the project coordinators.'
            )
          "
        >
          <div class="flex flex-col gap-2">
            <span class="text-base-medium text-ink-gray-8">{{
              __("Send to")
            }}</span>
            <ChipListInput
              v-model="form.status_report_recipients"
              doctype="User"
              :filters="{ enabled: 1, user_type: 'System User' }"
              :placeholder="__('Add a person')"
              mono
            />
          </div>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { __ } from "@/translation";
import { createResource, FormControl, Switch, toast } from "frappe-ui";
import { computed, ref } from "vue";
import ChipListInput from "../ChipListInput.vue";
import SettingRow from "../SettingRow.vue";
import SettingsSection from "../SettingsSection.vue";

interface TaskSettingsForm {
  ai_task_descriptions: boolean;
  ai_task_estimates: boolean;
  max_task_days: number;
  support_hours_email_customer: boolean;
  status_report_recipients: string[];
}

const DOCTYPE = "HD Work Settings";
const form = ref<TaskSettingsForm | null>(null);
const initial = ref("");

const settings = createResource({
  url: "frappe.client.get",
  params: { doctype: DOCTYPE, name: DOCTYPE },
  auto: true,
  onSuccess(doc) {
    form.value = {
      ai_task_descriptions: Boolean(doc.ai_task_descriptions),
      ai_task_estimates: Boolean(doc.ai_task_estimates),
      max_task_days: doc.max_task_days || 15,
      support_hours_email_customer: Boolean(doc.support_hours_email_customer),
      status_report_recipients: (doc.status_report_recipients || []).map(
        (row: { user: string }) => row.user
      ),
    };
    initial.value = JSON.stringify(form.value);
  },
});

const aiStatus = createResource({
  url: "helpdesk.task_descriptions.get_ai_status",
  cache: "tasky-ai-description-status",
  auto: true,
});

const isDirty = computed(
  () => !!form.value && JSON.stringify(form.value) !== initial.value
);

const save = createResource({
  url: "frappe.client.set_value",
  makeParams() {
    const f = form.value!;
    return {
      doctype: DOCTYPE,
      name: DOCTYPE,
      fieldname: {
        ai_task_descriptions: f.ai_task_descriptions ? 1 : 0,
        ai_task_estimates: f.ai_task_estimates ? 1 : 0,
        max_task_days: Math.max(Number(f.max_task_days) || 15, 1),
        support_hours_email_customer: f.support_hours_email_customer ? 1 : 0,
        status_report_recipients: f.status_report_recipients.map((user) => ({
          user,
        })),
      },
    };
  },
  onSuccess() {
    initial.value = JSON.stringify(form.value);
    toast.success(__("Task settings saved"));
  },
  onError(e: { messages?: string[] }) {
    toast.error(e.messages?.[0] || __("Couldn't save task settings"));
  },
});
</script>
