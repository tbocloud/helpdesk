<template>
  <div class="flex flex-col gap-4">
    <TaskyState
      v-if="f.options.error"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the form')"
      :message="
        errorText(f.options.error, __('Check your connection, then try again.'))
      "
    >
      <Button :label="__('Try again')" @click="f.options.reload()" />
    </TaskyState>

    <div
      v-else-if="!f.data"
      class="grid grid-cols-1 gap-4 lg:grid-cols-2"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div class="h-96 animate-pulse rounded-xl bg-surface-gray-1" />
      <div class="h-96 animate-pulse rounded-xl bg-surface-gray-1" />
    </div>

    <div
      v-else-if="!f.data.customer"
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

    <!-- left: everything to fill in; right: the mail and the document as they go out -->
    <form
      v-else
      class="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"
      novalidate
      @submit.prevent="askToSend"
    >
      <div class="flex min-w-0 flex-col gap-6">
        <SignoffFields :f="f" tall />
        <SignoffDetails :f="f" />

        <section
          class="flex flex-col gap-2"
          :aria-labelledby="`${id}-questions`"
        >
          <h3 :id="`${id}-questions`" class="text-base-medium text-ink-gray-9">
            {{ f.isUat ? __("Tests") : __("Questions") }}
          </h3>
          <p v-if="f.fromPlan && !f.editing" class="text-p-sm text-ink-gray-6">
            {{
              __(
                "The tests come from the approved SRS when the sign-off is saved; you can change them afterwards."
              )
            }}
          </p>
          <template v-else>
            <p class="text-p-sm text-ink-gray-6">
              {{
                __(
                  "Optional. The customer answers them on the questions page the mail links to; they accept the sign-off by replying to the mail."
                )
              }}
            </p>
            <SignoffQuestionsEditor
              :model-value="f.form.items"
              @update:model-value="f.setItems"
            />
          </template>
        </section>

        <div
          v-if="f.errorMessage"
          role="alert"
          class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
        >
          <LucideCircleAlert
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <span>{{ f.errorMessage }}</span>
        </div>

        <!-- the same buttons and rules as the dialog -->
        <div
          class="flex flex-col-reverse gap-2 border-t border-outline-gray-1 pt-4 sm:flex-row sm:items-center sm:justify-end"
        >
          <Button class="sm:mr-auto" :label="__('Back')" @click="emit('back')">
            <template #prefix
              ><LucideArrowLeft class="size-4" aria-hidden="true"
            /></template>
          </Button>
          <Button
            :label="f.editing ? __('Save changes') : __('Save as draft')"
            :loading="f.saving === 'draft'"
            :disabled="!!f.saving"
            @click="save(false)"
          />
          <Button
            v-if="f.data.can_send"
            variant="solid"
            :label="__('Send to customer')"
            :disabled="!!f.sendBlocked || !!f.saving"
            :title="f.sendBlocked || undefined"
            @click="askToSend"
          >
            <template #prefix
              ><LucideSend class="size-4" aria-hidden="true"
            /></template>
          </Button>
        </div>
        <p
          v-if="f.data.can_send && f.sendBlocked"
          class="-mt-4 text-right text-p-xs text-ink-gray-6"
        >
          {{ f.sendBlocked }}
        </p>
      </div>

      <SignoffPreview
        class="lg:sticky lg:top-4 lg:max-h-[calc(100vh-8rem)]"
        :mail="{
          subject: f.form.subject,
          toName: f.signatory?.full_name || '',
          toEmail: f.signatory?.email || '',
          cc: f.ccList,
          body: f.form.body,
        }"
        :unsaved="{ project: projectId, values: previewValues }"
      />
    </form>

    <SignoffSendConfirm
      v-model:open="confirmSend"
      :name="f.signatory?.full_name || ''"
      :email="f.signatory?.email || ''"
      :cc="f.ccList"
      :loading="f.saving === 'send'"
      @send="save(true)"
    />
  </div>
</template>

<script setup lang="ts">
import SignoffQuestionsEditor from "@/components/SignoffQuestionsEditor.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideArrowLeft from "~icons/lucide/arrow-left";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideSend from "~icons/lucide/send";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import {
  useSignoffForm,
  type CarriedSignoff,
  type SignoffSource,
} from "../useSignoffForm";
import SignoffDetails from "./SignoffDetails.vue";
import SignoffFields from "./SignoffFields.vue";
import SignoffPreview from "./SignoffPreview.vue";
import SignoffSendConfirm from "./SignoffSendConfirm.vue";

/** The full page's form (TBO's Sign-off requirements, Edit in full page): a new sign-off,
 * perhaps carried over from the dialog, or a draft (or changes requested) being edited. */
const props = defineProps<{
  projectId: string;
  uat?: boolean;
  signoff?: SignoffSource | null;
  carried?: CarriedSignoff | null;
}>();

const emit = defineEmits<{
  saved: [name: string, sent: boolean];
  back: [];
}>();

const id = `signoff-page-${useId()}`;
const f = useSignoffForm({
  projectId: () => props.projectId,
  uat: () => !!props.uat,
  signoff: () => props.signoff,
  withQuestions: true,
});
watch(
  () => props.signoff?.name,
  () => f.start(props.carried),
  { immediate: true }
);

// what the Document preview renders while nothing is saved yet
const previewValues = computed(() => ({
  signoff_type: f.isUat ? "UAT" : "Training",
  template: f.form.template,
  module_title: f.form.module_title,
  training_date: f.form.training_date,
  trainer: f.form.trainer,
  signatory_contact: f.form.signatory_contact,
  customer_address: f.form.customer_address,
  cc_emails: f.ccList.join(", "),
  details: f.detailPayload(),
  items: f.form.items,
}));

const confirmSend = ref(false);
function askToSend() {
  if (f.sendBlocked) {
    f.errorMessage = f.sendBlocked;
    return;
  }
  f.errorMessage = "";
  confirmSend.value = true;
}

async function save(send: boolean) {
  const name = await f.submit(send);
  confirmSend.value = false;
  if (name) emit("saved", name, send);
}
</script>
