<template>
  <SettingsLayoutBase
    :title="
      template ? form.template_name || template : __('New sign-off template')
    "
    :back-label="__('Back to sign-off templates')"
    :dirty="dirty"
    :save-label="template ? __('Save changes') : __('Create template')"
    :save-disabled="!canSave || (!!template && !dirty)"
    :saving="saving"
    :loading="!!template && !loaded && !detail.error"
    :error="detail.error"
    @retry="detail.reload()"
    @back="back"
    @save="save"
  >
    <template #header-actions>
      <Switch v-model="form.is_active" size="sm" :label="__('Active')" />
    </template>
    <template #content>
      <div class="flex flex-col gap-6">
        <SettingsSection :title="__('Details')">
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <TextInput
              v-model="form.template_name"
              :label="__('Name')"
              :placeholder="__('e.g. Accounts')"
              :disabled="!!template"
              maxlength="140"
              required
            />
            <TextInput
              v-model="form.module"
              :label="__('Module')"
              :placeholder="__('e.g. Accounts')"
              maxlength="140"
            />
          </div>
          <FormControl
            v-model="form.description"
            class="mt-4"
            type="textarea"
            :label="__('Description')"
            :rows="2"
            :description="__('For your team; customers don\'t see it.')"
          />
        </SettingsSection>
        <SettingsSection
          :title="__('Questions')"
          :description="
            __(
              'Write each one as something the customer can now do, e.g. \'I can record a Payment Entry against an invoice.\' Questions in the same section are shown together.'
            )
          "
        >
          <SignoffQuestionsEditor v-model="form.items" />
        </SettingsSection>
        <p v-if="error" role="alert" class="text-p-sm text-danger">
          {{ error }}
        </p>
      </div>
    </template>
  </SettingsLayoutBase>
  <ConfirmDialog
    v-model="confirmLeave"
    :title="__('Leave without saving?')"
    :message="
      __('Your changes on this page haven\'t been saved and will be lost.')
    "
    :on-confirm="() => emit('back')"
    :on-cancel="() => (confirmLeave = false)"
  />
</template>

<script setup lang="ts">
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import SignoffQuestionsEditor from "@/components/SignoffQuestionsEditor.vue";
import type { SignoffQuestion } from "@/pages/tasky/signoffMeta";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  FormControl,
  Switch,
  TextInput,
  call,
  createResource,
  toast,
} from "frappe-ui";
import { computed, reactive, ref } from "vue";
import SettingsSection from "../SettingsSection.vue";

const props = defineProps<{ template: string | null }>();
const emit = defineEmits<{ back: []; saved: [] }>();

const form = reactive({
  template_name: "",
  module: "",
  description: "",
  is_active: true,
  items: [] as SignoffQuestion[],
});
const loaded = ref(false);
const saved = ref("");
const saving = ref(false);
const error = ref("");

const snapshot = () => JSON.stringify(form);

const detail = createResource({
  url: "helpdesk.api.project_signoff.get_signoff_template",
  makeParams: () => ({ template: props.template }),
  auto: !!props.template,
  onSuccess(data) {
    Object.assign(form, {
      template_name: data.template_name,
      module: data.module || "",
      description: data.description || "",
      is_active: !!data.is_active,
      items: data.items,
    });
    saved.value = snapshot();
    loaded.value = true;
  },
  onError() {},
});
if (!props.template) saved.value = snapshot();

const dirty = computed(() => snapshot() !== saved.value);
const canSave = computed(
  () =>
    !!form.template_name.trim() &&
    form.items.every((i) => i.question.trim()) &&
    (!form.is_active || form.items.length > 0)
);

const confirmLeave = ref(false);

function back() {
  if (dirty.value) confirmLeave.value = true;
  else emit("back");
}

async function save() {
  if (!canSave.value) {
    error.value = __(
      "Give the template a name and every question some text. An active template needs at least one question."
    );
    return;
  }
  error.value = "";
  saving.value = true;
  try {
    await call("helpdesk.api.project_signoff.save_signoff_template", {
      template: props.template,
      template_name: form.template_name.trim(),
      module: form.module,
      description: form.description,
      is_active: form.is_active,
      items: form.items,
    });
    saved.value = snapshot();
    toast.success(__("Template saved"));
    emit("saved");
  } catch (e) {
    toast.error(errorText(e, __("Couldn't save the template.")));
  } finally {
    saving.value = false;
  }
}
</script>
