<template>
  <SettingsLayoutBase
    :description="__('How the AI helps when tasks are created.')"
  >
    <template #title>
      <div class="flex items-center gap-2">
        <h1 class="text-lg-semibold text-ink-gray-8">{{ __("Tasks") }}</h1>
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
          <h2 class="text-base-semibold text-ink-gray-9">{{ __("AI") }}</h2>
          <p
            v-if="aiStatus.data?.available === false"
            class="mt-2 flex items-start gap-2 text-p-sm text-ink-gray-6"
          >
            <LucideInfo
              class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
            {{ aiStatus.data.reason }}
          </p>
          <SettingRow
            :label="__('Write descriptions for new tasks with AI')"
            :description="
              __(
                'A task created without a description gets one in the background: the goal, the steps and when it is done. Text someone typed is never replaced.'
              )
            "
          >
            <Switch
              v-model="form.ai_task_descriptions"
              :aria-label="__('Write descriptions for new tasks with AI')"
            />
          </SettingRow>
          <SettingRow
            :label="__('AI sets the time for new tasks')"
            :description="
              __(
                'A task created without a due date gets working days and hours from the task, the project type and how long similar tasks took.'
              )
            "
          >
            <Switch
              v-model="form.ai_task_estimates"
              :aria-label="__('AI sets the time for new tasks')"
            />
          </SettingRow>
          <SettingRow
            v-if="form.ai_task_estimates"
            :label="__('Longest estimate')"
            :description="__('Working days.')"
          >
            <FormControl
              v-model="form.max_task_days"
              type="number"
              class="w-24"
              min="1"
              :aria-label="__('Longest estimate in working days')"
            />
          </SettingRow>
        </section>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
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
import LucideInfo from "~icons/lucide/info";
import SettingRow from "../Content/SettingRow.vue";
import { disableSettingModalOutsideClick } from "../settingsModal";

interface TaskSettingsForm {
  ai_task_descriptions: boolean;
  ai_task_estimates: boolean;
  max_task_days: number;
}

const DOCTYPE = "HD Work Settings";
const form = ref<TaskSettingsForm | null>(null);
const initial = ref("");

createResource({
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
watch(isDirty, (dirty) => (disableSettingModalOutsideClick.value = dirty));

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
