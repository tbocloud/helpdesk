<template>
  <Dialog
    :open="open"
    :title="__('Set category')"
    size="xl"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <p class="text-p-sm text-ink-gray-7">
        {{
          __(
            "Applies to the {0} selected leads. A field left as it is changes nothing; pick “Clear” to empty one.",
            String(leads.length)
          )
        }}
      </p>
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <LeadCategoryFields
          v-model:industry="form.industry"
          v-model:state="form.state"
          v-model:district="form.district"
          v-model:org-size="form.org_size"
          :options="options"
          :blank="__('Leave as it is')"
          :clearable="true"
        />
      </div>
      <div
        v-if="skipped.length"
        role="status"
        class="rounded-md bg-warning-soft px-3 py-2 text-p-sm text-ink-gray-8"
      >
        {{
          __(
            "{0} leads were left out: {1}",
            String(skipped.length),
            skipped.map((s) => `${s.name} (${s.reason})`).join(", ")
          )
        }}
      </div>
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
          :label="__('Set category')"
          :loading="saving"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, Dialog, toast } from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LeadCategoryFields from "./LeadCategoryFields.vue";
import { CLEAR, leadOptions, type LeadOptions } from "./leads";

const props = defineProps<{ open: boolean; leads: string[] }>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  (e: "saved"): void;
}>();

const formId = `set-category-${useId()}`;
const options = computed(() => leadOptions.data as LeadOptions | undefined);
const form = reactive({ industry: "", state: "", district: "", org_size: "" });
const errorMessage = ref("");
const skipped = ref<{ name: string; reason: string }[]>([]);
const saving = ref(false);

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    Object.assign(form, {
      industry: "",
      state: "",
      district: "",
      org_size: "",
    });
    errorMessage.value = "";
    skipped.value = [];
  }
);

function submit() {
  if (saving.value) return;
  // "" is left as it is; the CLEAR choice empties the field on the ERP site
  const values = Object.fromEntries(
    Object.entries(form)
      .filter(([, v]) => v)
      .map(([k, v]) => [k, v === CLEAR ? "" : v])
  );
  if (!Object.keys(values).length) {
    errorMessage.value = __("Choose at least one thing to set.");
    return;
  }
  errorMessage.value = "";
  saving.value = true;
  call("helpdesk.api.leads.bulk_set_lead_category", {
    leads: props.leads,
    values,
  })
    .then((result: { updated: number; skipped: typeof skipped.value }) => {
      toast.success(__("{0} leads updated", String(result.updated)));
      emit("saved");
      if (result.skipped?.length) skipped.value = result.skipped;
      else emit("update:open", false);
    })
    .catch((e: unknown) => {
      errorMessage.value = errorText(
        e,
        __("Couldn't set the category. Check your connection and try again.")
      );
    })
    .finally(() => (saving.value = false));
}
</script>
