<template>
  <Dialog
    :open="open"
    :title="__('Hand back credentials and close the project')"
    size="lg"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <p class="text-p-sm text-ink-gray-6">
        {{
          __(
            "Every login the client handed over is listed as returned, and the client signs it off. The project is then closed as Cancelled. This can't be undone."
          )
        }}
      </p>
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <TextInput
          v-model="form.client_signoff_name"
          :label="__('Signed off by (at the client)')"
          maxlength="140"
          required
        />
        <TextInput
          v-model="form.signed_on"
          type="date"
          :label="__('Signed on')"
          :max="today"
          required
        />
      </div>
      <FormControl
        v-model="form.reason"
        type="textarea"
        :rows="3"
        :label="__('Why is the project closing?')"
        required
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
          theme="red"
          type="submit"
          :form="formId"
          :label="__('Hand back and close')"
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

const props = defineProps<{ open: boolean; projectId: string }>();
const emit = defineEmits<{
  "update:open": [value: boolean];
  done: [];
}>();

const formId = `hand-back-form-${useId()}`;
const today = new Date().toISOString().slice(0, 10);
const errorMessage = ref("");
const saving = ref(false);
const form = reactive({
  client_signoff_name: "",
  signed_on: today,
  reason: "",
});

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    errorMessage.value = "";
    Object.assign(form, {
      client_signoff_name: "",
      signed_on: today,
      reason: "",
    });
  }
);

async function submit() {
  if (
    !form.client_signoff_name.trim() ||
    !form.signed_on ||
    !form.reason.trim()
  ) {
    errorMessage.value = __(
      "Fill in who signed off, the date, and why the project is closing."
    );
    return;
  }
  errorMessage.value = "";
  saving.value = true;
  try {
    await call("helpdesk.api.client_credentials.hand_back_and_close", {
      project: props.projectId,
      ...form,
    });
    toast.success(__("Credentials handed back. The project is closed."));
    emit("update:open", false);
    emit("done");
  } catch (e) {
    errorMessage.value = errorText(e, __("Couldn't hand back. Try again."));
  } finally {
    saving.value = false;
  }
}
</script>
