<template>
  <SettingsLayoutBase
    :title="__('Tasks')"
    :description="__('How the AI helps when tasks are created.')"
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
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { __ } from "@/translation";
import { createResource, FormControl, Switch, toast } from "frappe-ui";
import { computed, ref } from "vue";
import SettingRow from "../SettingRow.vue";
import SettingsSection from "../SettingsSection.vue";

interface TaskSettingsForm {
  ai_task_descriptions: boolean;
  ai_task_estimates: boolean;
  max_task_days: number;
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
