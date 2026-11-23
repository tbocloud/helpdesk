<template>
  <Dialog
    :open="open"
    :title="__('New expense claim')"
    size="lg"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <form :id="formId" class="flex flex-col gap-4" @submit.prevent="submit">
      <FormControl
        v-model="form.expense_type"
        type="select"
        size="md"
        :label="__('Type')"
        :options="typeOptions"
        required
      />
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl
          v-model="form.amount"
          type="number"
          size="md"
          min="0.01"
          step="0.01"
          inputmode="decimal"
          :label="__('Amount ({0})', currencySymbol(currency))"
          required
        />
        <FormControl
          v-model="form.expense_date"
          type="date"
          size="md"
          :max="today"
          :label="__('Spent on')"
          required
        />
      </div>
      <FormControl
        v-model="form.description"
        type="textarea"
        size="md"
        :rows="2"
        :label="__('What was it for?')"
        :placeholder="__('Client visit to Kochi, auto fare')"
      />

      <div class="flex flex-col gap-1.5">
        <span :id="receiptLabel" class="text-xs text-ink-gray-6">
          {{ __("Receipt") }}
        </span>
        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="md"
            :aria-describedby="receiptLabel"
            :label="receipt ? __('Change receipt') : __('Add a receipt')"
            @click="fileInput?.click()"
          >
            <template #prefix>
              <LucidePaperclip class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <span
            v-if="receipt"
            class="min-w-0 truncate text-sm text-ink-gray-7"
            :title="receipt.filename"
          >
            {{ receipt.filename }}
          </span>
          <span v-else class="text-sm text-ink-gray-6">
            {{ __("A photo or PDF of the bill") }}
          </span>
        </div>
        <input
          ref="fileInput"
          type="file"
          class="hidden"
          accept="image/*,application/pdf"
          @change="pickReceipt"
        />
      </div>

      <p v-if="errorMessage" role="alert" class="text-p-sm text-danger">
        {{ errorMessage }}
      </p>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Send for approval')"
          :loading="saving || readingReceipt"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { currencySymbol } from "@/pages/sales-targets/salesTargets";
import { preparePhoto, readBase64 } from "@/pages/leads/place";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, dayjs, Dialog, FormControl, toast } from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucidePaperclip from "~icons/lucide/paperclip";
import type { Claim } from "./expenses";

const MAX_RECEIPT_BYTES = 10 * 1024 * 1024;

const props = defineProps<{
  open: boolean;
  types: string[];
  currency: string;
}>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  (e: "created", claim: Claim): void;
}>();

const formId = useId();
const receiptLabel = useId();
const today = dayjs().format("YYYY-MM-DD");
const fileInput = ref<HTMLInputElement | null>(null);

const form = reactive({
  expense_type: "",
  amount: "" as string | number,
  expense_date: today,
  description: "",
});
const receipt = ref<{ filename: string; content: string } | null>(null);
const readingReceipt = ref(false);
const saving = ref(false);
const errorMessage = ref("");

const typeOptions = computed(() => [
  { label: __("Choose a type"), value: "", disabled: true },
  ...props.types.map((type) => ({ label: type, value: type })),
]);

// each time it opens, a fresh claim
watch(
  () => props.open,
  (open) => {
    if (!open) return;
    Object.assign(form, {
      expense_type: props.types.length === 1 ? props.types[0] : "",
      amount: "",
      expense_date: today,
      description: "",
    });
    receipt.value = null;
    errorMessage.value = "";
  }
);

async function pickReceipt(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  errorMessage.value = "";
  readingReceipt.value = true;
  try {
    if (file.type === "application/pdf") {
      if (file.size > MAX_RECEIPT_BYTES)
        throw new Error(__("The receipt is larger than 10 MB."));
      receipt.value = { filename: file.name, content: await readBase64(file) };
    } else {
      // a phone photo is scaled down and sent as JPEG
      receipt.value = await preparePhoto(file);
    }
  } catch (e) {
    errorMessage.value = errorText(e, __("Couldn't read that file."));
  } finally {
    readingReceipt.value = false;
  }
}

async function submit() {
  if (saving.value || readingReceipt.value) return;
  if (!form.expense_type) {
    errorMessage.value = __("Choose the type of expense.");
    return;
  }
  if (!(Number(form.amount) > 0)) {
    errorMessage.value = __("Enter the amount you spent.");
    return;
  }
  errorMessage.value = "";
  saving.value = true;
  try {
    const claim = await call("helpdesk.api.expenses.create_expense_claim", {
      expense_type: form.expense_type,
      amount: Number(form.amount),
      expense_date: form.expense_date,
      description: form.description,
      receipt_filename: receipt.value?.filename,
      receipt_base64: receipt.value?.content,
    });
    toast.success(
      __("Claim sent to {0}", claim.approver || __("your approver"))
    );
    emit("created", claim);
    emit("update:open", false);
  } catch (e) {
    errorMessage.value = errorText(
      e,
      __("Couldn't send the claim. Try again.")
    );
  } finally {
    saving.value = false;
  }
}
</script>
