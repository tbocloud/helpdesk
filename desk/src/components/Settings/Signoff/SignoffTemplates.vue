<template>
  <SignoffTemplateEditor
    v-if="editing !== null"
    :template="editing || null"
    @back="closeEditor"
    @saved="onSaved"
  />
  <SettingsLayoutBase
    v-else
    :title="__('Sign-off templates')"
    :description="
      __(
        'The questions a customer answers to confirm a training is complete. A new sign-off copies a template\'s questions, so editing a template never changes a sign-off already sent.'
      )
    "
  >
    <template #header-actions>
      <Button variant="solid" :label="__('New template')" @click="editing = ''">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <template #content>
      <SettingsList
        :items="templates.data"
        :label="__('Sign-off templates')"
        :loading="templates.loading"
        :error="templates.error"
        :empty-icon="LucideClipboardCheck"
        :empty-title="__('No sign-off templates yet')"
        :empty-message="
          __('Make one per module you train customers on, e.g. Accounts or HR.')
        "
        @retry="templates.reload()"
      >
        <template #default="{ item }">
          <SettingsListItem
            :title="item.template_name"
            :subtitle="subtitle(item)"
            :muted="!item.is_active"
            @open="editing = item.name"
          >
            <template #badges>
              <TaskyBadge v-if="!item.is_active" :label="__('Inactive')" />
            </template>
          </SettingsListItem>
        </template>
      </SettingsList>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { Button, createResource } from "frappe-ui";
import { ref } from "vue";
import LucideClipboardCheck from "~icons/lucide/clipboard-check";
import LucidePlus from "~icons/lucide/plus";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";
import SignoffTemplateEditor from "./SignoffTemplateEditor.vue";

interface TemplateRow {
  name: string;
  template_name: string;
  module?: string | null;
  is_active: number;
  question_count: number;
}

/** null: the list; "": a new template; a name: that template. */
const editing = ref<string | null>(null);

const templates = createResource({
  url: "helpdesk.api.project_signoff.get_signoff_templates",
  auto: true,
  onError() {},
});

function subtitle(t: TemplateRow) {
  const count =
    t.question_count === 1
      ? __("1 question")
      : __("{0} questions", String(t.question_count));
  return t.module ? `${t.module} · ${count}` : count;
}

function closeEditor() {
  editing.value = null;
}

function onSaved() {
  templates.reload();
  editing.value = null;
}
</script>
