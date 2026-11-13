<template>
  <Dialog v-model:open="open" :title="__('New dashboard')" size="lg">
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="create"
    >
      <fieldset class="flex flex-col gap-2">
        <legend class="mb-1 text-sm text-ink-gray-7">
          {{ __("Start from") }}
        </legend>
        <label
          v-for="(template, key) in templates"
          :key="key"
          class="flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5"
          :class="
            picked === key
              ? 'border-brand bg-brand-soft'
              : 'border-outline-gray-2 hover:border-outline-gray-4'
          "
        >
          <input
            v-model="picked"
            type="radio"
            name="template"
            :value="key"
            class="mt-1 size-4 focus-visible:ring-2 focus-visible:ring-highlight"
          />
          <span class="flex min-w-0 flex-col">
            <span
              class="text-base-medium"
              :class="picked === key ? 'text-brand-ink' : 'text-ink-gray-9'"
              >{{ template.label }}</span
            >
            <span class="text-p-sm text-ink-gray-6">{{
              template.description
            }}</span>
          </span>
        </label>
      </fieldset>
      <FormControl
        v-model="name"
        :label="__('Name')"
        :placeholder="templates[picked]?.label"
        maxlength="140"
        required
        autocomplete="off"
      />
      <p
        v-if="error"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ error }}</span>
      </p>
    </form>
    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Create dashboard')"
          :loading="creating"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, Dialog, FormControl } from "frappe-ui";
import { ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import type { Registry } from "./crmDashboards";

const props = defineProps<{ templates: Registry["templates"] }>();
const emit = defineEmits<{ created: [name: string] }>();
const open = defineModel<boolean>("open", { required: true });

const formId = `new-crm-dashboard-${useId()}`;
const picked = ref(Object.keys(props.templates)[0] || "");
const name = ref("");
const error = ref("");
const creating = ref(false);

watch(open, (isOpen) => {
  if (isOpen) {
    name.value = "";
    error.value = "";
  }
});

async function create() {
  const dashboardName =
    name.value.trim() || props.templates[picked.value]?.label;
  if (!dashboardName || creating.value) return;
  creating.value = true;
  error.value = "";
  try {
    const config = await call(
      "helpdesk.api.crm_dashboard_settings.create_dashboard",
      { template: picked.value, dashboard_name: dashboardName }
    );
    emit("created", config.name);
  } catch (e) {
    error.value = errorText(e, __("Couldn't create the dashboard. Try again."));
  } finally {
    creating.value = false;
  }
}
</script>
