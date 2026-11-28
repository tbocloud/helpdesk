<template>
  <Dialog
    :open="open"
    :title="entry ? __('Edit entry') : __('Add an entry')"
    size="xl"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl
          v-model="form.kind"
          type="select"
          :label="__('Kind')"
          :options="kinds"
        />
        <FormControl
          v-model="form.environment"
          type="select"
          :label="__('Environment')"
          :options="environments"
        />
      </div>
      <TextInput
        v-model="form.label"
        :label="__('Name')"
        :placeholder="
          __('e.g. Backend repository, Demo login, Production server')
        "
        maxlength="140"
        required
      />
      <TextInput
        v-model="form.url"
        :label="__('URL')"
        placeholder="https://"
        inputmode="url"
      />
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <TextInput
          v-model="form.username"
          :label="__('Username')"
          autocomplete="off"
        />
        <TextInput
          v-model="form.password"
          type="password"
          autocomplete="new-password"
          :label="__('Password')"
          :placeholder="
            entry?.has_password ? __('Leave empty to keep the saved one') : ''
          "
        />
      </div>
      <label
        v-if="entry?.has_password && !form.password"
        class="flex items-center gap-2 text-p-sm text-ink-gray-7"
      >
        <input v-model="form.clear_password" type="checkbox" />
        {{ __("Remove the saved password") }}
      </label>
      <FormControl
        v-model="form.notes"
        type="textarea"
        :rows="3"
        :label="__('Notes')"
        :placeholder="
          __(
            'Branch, how to deploy, who at the client to ask, SSH key location…'
          )
        "
      />

      <div
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ errorMessage }}</span>
      </div>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Save')"
          :loading="saving"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, Dialog, FormControl, TextInput, call, toast } from "frappe-ui";
import { reactive, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import type { AccessEntry } from "../projectAccessMeta";

const props = defineProps<{
  open: boolean;
  projectId: string;
  kinds: string[];
  environments: string[];
  /** the entry to change; without it the dialog adds a new one */
  entry?: AccessEntry | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  saved: [];
}>();

const formId = `access-form-${useId()}`;
const errorMessage = ref("");
const saving = ref(false);

const form = reactive({
  kind: "",
  environment: "",
  label: "",
  url: "",
  username: "",
  password: "",
  clear_password: false,
  notes: "",
});

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    errorMessage.value = "";
    const e = props.entry;
    Object.assign(form, {
      kind: e?.kind ?? props.kinds[0] ?? "Other",
      environment: e?.environment ?? props.environments[0] ?? "",
      label: e?.label ?? "",
      url: e?.url ?? "",
      username: e?.username ?? "",
      password: "",
      clear_password: false,
      notes: e?.notes ?? "",
    });
  },
  { immediate: true }
);

async function submit() {
  if (!form.label.trim()) {
    errorMessage.value = __(
      'Give it a name, e.g. "Backend repository" or "Demo login".'
    );
    return;
  }
  errorMessage.value = "";
  saving.value = true;
  try {
    await call("helpdesk.api.project_access.save_access_entry", {
      project: props.projectId,
      name: props.entry?.name,
      entry: { ...form, clear_password: form.clear_password ? 1 : 0 },
    });
    toast.success(__("Saved"));
    emit("update:open", false);
    emit("saved");
  } catch (e) {
    errorMessage.value = errorText(e, __("Couldn't save. Try again."));
  } finally {
    saving.value = false;
  }
}
</script>
