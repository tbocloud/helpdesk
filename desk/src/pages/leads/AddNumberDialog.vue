<template>
  <Dialog
    :open="open"
    :title="__('Add a number')"
    size="sm"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <FormControl
        v-model="form.number"
        type="tel"
        inputmode="tel"
        :label="__('Phone number')"
        :placeholder="__('+91 98470 12345')"
        autocomplete="off"
        required
        @input="checkSoon"
        @blur="checkSoon"
      />
      <DuplicateLeadsNotice
        :matches="duplicates"
        :title="__('This number is on another lead too. You can still add it.')"
      />
      <FormControl
        v-model="form.label"
        type="select"
        :label="__('Whose number is it?')"
        :options="labelChoices"
      />
      <FormControl
        v-model="form.person"
        :label="__('Name (optional)')"
        maxlength="140"
        autocomplete="off"
      />
      <FormControl
        v-model="form.note"
        :label="__('Note (optional)')"
        :placeholder="__('Best time to call, who to ask for')"
        maxlength="140"
        autocomplete="off"
      />
      <FormControl
        v-model="form.make_primary"
        type="checkbox"
        :label="__('Make this the main number')"
      />
      <p v-if="form.make_primary" class="-mt-2 text-p-xs text-ink-gray-6">
        {{ __("The old main number stays on the lead, under Old numbers.") }}
      </p>
      <p v-if="error" role="alert" class="text-p-sm text-danger">
        {{ error }}
      </p>
    </form>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="emit('update:open', false)" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Save')"
          :disabled="!form.number.trim()"
          :loading="addNumber.loading"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useDebounceFn } from "@vueuse/core";
import {
  Button,
  call,
  createResource,
  Dialog,
  FormControl,
  toast,
} from "frappe-ui";
import { reactive, ref, useId, watch } from "vue";
import DuplicateLeadsNotice from "./DuplicateLeadsNotice.vue";
import { NUMBER_LABELS, type DuplicateLead } from "./leads";

const props = defineProps<{
  open: boolean;
  leadId: string;
  /** the number was heard on a call, so it is recorded as added on a call */
  onCall?: boolean;
}>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  (e: "saved"): void;
}>();

const formId = `add-number-${useId()}`;
const labelChoices = NUMBER_LABELS.map((l) => ({
  label: l.label,
  value: l.value,
}));
const MIN_DIGITS = 7;

function blank() {
  return {
    number: "",
    label: "Mobile",
    person: "",
    note: "",
    make_primary: false,
  };
}
const form = reactive(blank());
const error = ref("");

// other leads that already have the number (the ERP site finds them; a warning, not a stop)
const duplicates = ref<DuplicateLead[]>([]);
let checkedFor = "";

async function checkDuplicates() {
  const phone = form.number.trim();
  if (phone === checkedFor) return;
  checkedFor = phone;
  if (phone.replace(/\D/g, "").length < MIN_DIGITS) {
    duplicates.value = [];
    return;
  }
  try {
    const result: { matches?: DuplicateLead[] } = await call(
      "helpdesk.api.leads.find_duplicate_leads",
      { phone, exclude: props.leadId }
    );
    // the person kept typing while it was asked
    if (checkedFor === phone) duplicates.value = result?.matches ?? [];
  } catch {
    if (checkedFor === phone) duplicates.value = [];
  }
}
const checkSoon = useDebounceFn(checkDuplicates, 400);

// each time it opens it starts empty (the dialog puts the cursor in the number)
watch(
  () => props.open,
  (open) => {
    if (!open) return;
    Object.assign(form, blank());
    error.value = "";
    duplicates.value = [];
    checkedFor = "";
  }
);

const addNumber = createResource({
  url: "helpdesk.api.leads.add_lead_number",
  method: "POST",
  onSuccess() {
    toast.success(__("Number added"));
    emit("update:open", false);
    emit("saved");
  },
  onError(e: unknown) {
    error.value = errorText(
      e,
      __("Couldn't add the number. Check it and try again.")
    );
  },
});

function submit() {
  if (addNumber.loading || !form.number.trim()) return;
  error.value = "";
  addNumber.submit({
    lead: props.leadId,
    number: form.number,
    label: form.label,
    person: form.person,
    note: form.note,
    make_primary: form.make_primary ? 1 : 0,
    on_call: props.onCall ? 1 : 0,
  });
}
</script>
