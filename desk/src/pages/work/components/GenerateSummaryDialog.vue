<template>
  <!-- the customer picker's dropdown renders outside the dialog, so an
       outside click must not close it; Cancel and the close button still do -->
  <Dialog
    v-model:open="open"
    :title="__('Generate summary now')"
    size="md"
    :dismissible="false"
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
            "Summarises the customer's tickets, tasks and projects for the last 7 days, including today. With AI this can take up to a minute."
          )
        }}
      </p>
      <Link
        v-model="customer"
        doctype="HD Customer"
        :label="__('Customer')"
        :placeholder="__('Select customer')"
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
          :label="__('Generate')"
          :loading="generate.loading"
          :disabled="!customer || generate.loading"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import { Link } from "@/components";
import { __ } from "@/translation";
import { Button, createResource, Dialog, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import { type SummaryDetail } from "../summaryMeta";

const props = defineProps<{ defaultCustomer?: string }>();
const emit = defineEmits<{ generated: [summary: SummaryDetail] }>();
const open = defineModel<boolean>("open", { default: false });

const formId = `generate-summary-${useId()}`;
const customer = ref("");

const generate = createResource({
  url: "helpdesk.api.work_summary.generate_summary",
  onSuccess(data: SummaryDetail) {
    toast.success(__("Summary generated"));
    open.value = false;
    emit("generated", data);
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});

const errorMessage = computed(() =>
  errorText(generate.error, __("Couldn't generate the summary."))
);

watch(open, (isOpen) => {
  if (!isOpen) return;
  customer.value = props.defaultCustomer ?? "";
  generate.reset();
});

watch(customer, () => {
  if (generate.error) generate.reset();
});

function submit() {
  if (!customer.value || generate.loading) return;
  generate.submit({ customer: customer.value });
}
</script>
