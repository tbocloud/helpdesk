<template>
  <Dialog
    :open="open"
    :title="editing ? __('Edit sign-off') : __('New sign-off')"
    :size="editing ? '4xl' : 'xl'"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <TaskyState
      v-if="options.error"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the form')"
      :message="
        errorText(options.error, __('Check your connection, then try again.'))
      "
    >
      <Button :label="__('Try again')" @click="options.reload()" />
    </TaskyState>

    <div
      v-else-if="!options.data"
      class="flex flex-col gap-4"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div v-for="i in 4" :key="i" class="flex flex-col gap-1.5">
        <div class="h-3 w-24 animate-pulse rounded bg-surface-gray-2" />
        <div class="h-8 w-full animate-pulse rounded bg-surface-gray-1" />
      </div>
    </div>

    <div
      v-else-if="!options.data.customer"
      role="alert"
      class="flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-p-sm text-warning"
    >
      <LucideTriangleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{{
        __(
          "This project has no customer. Set the customer on the project first; the person who signs off must be one of its contacts."
        )
      }}</span>
    </div>

    <form
      v-else
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl
          v-if="!editing"
          v-model="form.template"
          type="select"
          :label="__('Template')"
          :options="templateOptions"
          :description="
            __(
              'Its questions are copied in; you can change them before sending.'
            )
          "
          @update:model-value="onTemplate"
        />
        <TextInput
          v-model="form.module_title"
          :label="__('Module')"
          :placeholder="__('e.g. Accounts')"
          maxlength="140"
          required
        />
        <TextInput
          v-model="form.training_date"
          type="date"
          :label="__('Training date')"
        />
        <!-- Combobox layers inside the dialog, so Escape and clicking outside still close it -->
        <Combobox
          :label="__('Trainer')"
          :options="trainerOptions"
          :placeholder="__('Pick from the project team')"
          :model-value="form.trainer || null"
          @update:model-value="(v: string | null) => (form.trainer = v || '')"
        />
        <div class="flex flex-col gap-1.5 sm:col-span-2">
          <Combobox
            :label="__('Signs off for the customer')"
            :options="contactOptions"
            :placeholder="__('Pick a contact of {0}', options.data.customer)"
            :empty-text="__('No contacts with an email')"
            :model-value="form.signatory_contact || null"
            @update:model-value="
              (v: string | null) => (form.signatory_contact = v || '')
            "
          />
          <p class="text-p-xs text-ink-gray-5">
            <template v-if="options.data.contacts.length">
              {{
                __(
                  "Only this person gets the link and the one-time code, and only they can sign."
                )
              }}
            </template>
            <template v-else>
              {{
                __(
                  "{0} has no contacts with an email yet.",
                  options.data.customer
                )
              }}
              <router-link
                :to="{
                  name: 'Customer',
                  params: { id: options.data.customer },
                }"
                class="rounded text-ink-gray-8 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                >{{ __("Add contacts to the customer") }}</router-link
              >
            </template>
          </p>
        </div>
      </div>

      <section v-if="editing" class="flex flex-col gap-2">
        <h3 class="text-base-medium text-ink-gray-9">{{ __("Questions") }}</h3>
        <SignoffQuestionsEditor v-model="form.items" />
      </section>

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
          v-if="options.data?.customer"
          variant="solid"
          type="submit"
          :form="formId"
          :label="editing ? __('Save changes') : __('Create sign-off')"
          :loading="saving"
          :disabled="!canSubmit"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import SignoffQuestionsEditor from "@/components/SignoffQuestionsEditor.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  Combobox,
  Dialog,
  FormControl,
  TextInput,
  call,
  createResource,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import type { SignoffQuestion } from "../signoffMeta";

/** The sign-off being edited (Draft or Reopened); without it the dialog creates one. */
export interface SignoffDraft {
  name: string;
  module_title: string;
  training_date?: string | null;
  trainer?: string | null;
  signatory_contact?: string | null;
  items: SignoffQuestion[];
}

const props = defineProps<{
  open: boolean;
  projectId: string;
  signoff?: SignoffDraft | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  saved: [name: string];
}>();

const formId = `signoff-form-${useId()}`;
const editing = computed(() => !!props.signoff);
const errorMessage = ref("");

const form = reactive({
  template: "",
  module_title: "",
  training_date: "",
  trainer: "",
  signatory_contact: "",
  items: [] as SignoffQuestion[],
});

const options = createResource({
  url: "helpdesk.api.project_signoff.get_signoff_form",
  makeParams: () => ({ project: props.projectId }),
});

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    errorMessage.value = "";
    const s = props.signoff;
    Object.assign(form, {
      template: "",
      module_title: s?.module_title ?? "",
      training_date: s?.training_date ?? "",
      trainer: s?.trainer ?? "",
      signatory_contact: s?.signatory_contact ?? "",
      items: s ? s.items.map((i) => ({ ...i })) : [],
    });
    options.reload();
  },
  { immediate: true }
);

const templateOptions = computed(() => [
  { label: __("No template: start empty"), value: "" },
  ...(options.data?.templates ?? []).map(
    (t: { name: string; template_name: string }) => ({
      label: t.template_name,
      value: t.name,
    })
  ),
]);

const trainerOptions = computed(() =>
  (options.data?.team ?? []).map((m: { user: string; full_name: string }) => ({
    label: m.full_name || m.user,
    value: m.user,
    description: m.user,
  }))
);

const contactOptions = computed(() =>
  (options.data?.contacts ?? []).map(
    (c: { contact: string; full_name: string; email: string }) => ({
      label: c.full_name,
      value: c.contact,
      description: c.email,
    })
  )
);

function onTemplate(name: string) {
  const t = (options.data?.templates ?? []).find(
    (x: { name: string }) => x.name === name
  );
  // suggest the template's module, without overwriting what was typed
  if (t?.module && !form.module_title.trim()) form.module_title = t.module;
}

const canSubmit = computed(
  () =>
    !!form.module_title.trim() &&
    !!form.trainer &&
    !!form.signatory_contact &&
    (!editing.value ||
      (form.items.length > 0 && form.items.every((i) => i.question.trim())))
);

const saving = ref(false);

async function submit() {
  if (!canSubmit.value) {
    errorMessage.value = editing.value
      ? __(
          "Fill in the module, trainer and signatory, and give every question some text."
        )
      : __("Fill in the module, trainer and signatory.");
    return;
  }
  errorMessage.value = "";
  const common = {
    module_title: form.module_title.trim(),
    training_date: form.training_date || null,
    trainer: form.trainer,
    signatory_contact: form.signatory_contact,
  };
  saving.value = true;
  try {
    const data: { name: string } = editing.value
      ? await call("helpdesk.api.project_signoff.update_signoff", {
          signoff: props.signoff!.name,
          items: form.items,
          ...common,
        })
      : await call("helpdesk.api.project_signoff.create_signoff", {
          project: props.projectId,
          template: form.template || null,
          ...common,
        });
    toast.success(
      editing.value ? __("Sign-off saved") : __("Sign-off created")
    );
    emit("update:open", false);
    emit("saved", data.name);
  } catch (e) {
    errorMessage.value = errorText(e, __("Couldn't save the sign-off."));
  } finally {
    saving.value = false;
  }
}
</script>
