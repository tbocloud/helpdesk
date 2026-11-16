<template>
  <!-- one detail of the sign-off's stage, drawn from the doctype's own field (its label,
       type and choices come from get_signoff_form's `fields`) -->
  <div v-if="meta" :class="wide ? 'sm:col-span-2' : ''">
    <!-- services, platforms: the requirements' choices as chips -->
    <fieldset v-if="choices" class="flex flex-col gap-1.5">
      <legend class="mb-1.5 text-xs text-ink-gray-5">
        {{ label }}<span v-if="required" aria-hidden="true"> *</span>
      </legend>
      <div class="flex flex-wrap gap-1.5">
        <ChipToggle
          v-for="choice in choices"
          :key="choice"
          :label="__(choice)"
          :pressed="picked.includes(choice)"
          @toggle="toggle(choice)"
        />
      </div>
    </fieldset>

    <!-- modules in the dialog: a multi-select of ERPNext modules; the full page has the table -->
    <fieldset
      v-else-if="field === 'modules' && compact"
      class="flex flex-col gap-1.5"
    >
      <legend class="mb-1.5 text-xs text-ink-gray-5">
        {{ label }}<span v-if="required" aria-hidden="true"> *</span>
      </legend>
      <div class="flex flex-wrap gap-1.5">
        <ChipToggle
          v-for="module in moduleChoices"
          :key="module"
          :label="__(module)"
          :pressed="moduleNames.includes(module)"
          @toggle="toggleModule(module)"
        />
      </div>
    </fieldset>

    <div v-else-if="meta.fieldtype === 'Table'" class="flex flex-col gap-1.5">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <span class="text-xs text-ink-gray-5"
          >{{ label }}<span v-if="required" aria-hidden="true"> *</span></span
        >
        <!-- deliverables can come from the content calendar (the requirements: "pulled") -->
        <Button
          v-if="field === 'deliverables'"
          size="sm"
          :label="__('Fill from the content calendar')"
          :loading="f.pulling"
          @click="f.pullDeliverables()"
        />
      </div>
      <SignoffTable
        :meta="meta"
        :model-value="(f.detail(field) as Record<string, unknown>[]) ?? []"
        @update:model-value="(rows) => f.setDetail(field, rows)"
      />
    </div>

    <Combobox
      v-else-if="field === 'trainer'"
      :label="f.isUat ? __('Tests with the client') : label"
      :options="f.trainerOptions"
      :placeholder="__('Pick from the project team')"
      :model-value="(f.detail(field) as string) || null"
      @update:model-value="(v: string | null) => f.setDetail(field, v || '')"
    />

    <Checkbox
      v-else-if="meta.fieldtype === 'Check'"
      :label="label"
      :model-value="!!f.detail(field)"
      @update:model-value="(v: boolean) => f.setDetail(field, v ? 1 : 0)"
    />

    <FormControl
      v-else-if="meta.fieldtype === 'Select'"
      type="select"
      :label="label"
      :options="selectOptions"
      :model-value="(f.detail(field) as string) ?? ''"
      @update:model-value="(v: string) => f.setDetail(field, v)"
    />

    <FormControl
      v-else-if="meta.fieldtype === 'Small Text'"
      type="textarea"
      :rows="3"
      :label="label"
      :model-value="(f.detail(field) as string) ?? ''"
      @update:model-value="(v: string) => f.setDetail(field, v)"
    />

    <!-- the delivery report: a file uploaded once, kept private -->
    <div v-else-if="meta.fieldtype === 'Attach'" class="flex flex-col gap-1.5">
      <span class="text-xs text-ink-gray-5">{{ label }}</span>
      <div class="flex flex-wrap items-center gap-2">
        <a
          v-if="f.detail(field)"
          :href="String(f.detail(field))"
          target="_blank"
          rel="noopener"
          class="truncate rounded text-sm text-ink-gray-8 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          >{{ String(f.detail(field)).split("/").pop() }}</a
        >
        <FileUploader
          :upload-args="{ private: true }"
          @success="(file: { file_url: string }) => f.setDetail(field, file.file_url)"
        >
          <template #default="{ openFileSelector, uploading }">
            <Button
              size="sm"
              :label="f.detail(field) ? __('Replace') : __('Upload')"
              :loading="uploading"
              @click="openFileSelector()"
            />
          </template>
        </FileUploader>
        <Button
          v-if="f.detail(field)"
          size="sm"
          variant="ghost"
          :label="__('Remove')"
          @click="f.setDetail(field, '')"
        />
      </div>
    </div>

    <TextInput
      v-else
      :type="inputType"
      :label="required ? `${label} *` : label"
      :placeholder="placeholder"
      :model-value="(f.detail(field) as string) ?? ''"
      @update:model-value="(v: string) => f.setDetail(field, v)"
    />

    <p v-if="meta.description" class="mt-1 text-p-xs text-ink-gray-5">
      {{ meta.description }}
    </p>
  </div>
</template>

<script setup lang="ts">
import ChipToggle from "@/pages/content/components/ChipToggle.vue";
import { __ } from "@/translation";
import {
  Button,
  Checkbox,
  Combobox,
  FileUploader,
  FormControl,
  TextInput,
} from "frappe-ui";
import { computed } from "vue";
import { splitChoices, type SignoffForm } from "../useSignoffForm";
import SignoffTable from "./SignoffTable.vue";

const props = defineProps<{
  f: SignoffForm;
  field: string;
  /** the dialog: modules as a multi-select rather than the table */
  compact?: boolean;
}>();

const meta = computed(() => props.f.data?.fields[props.field]);
const label = computed(() => meta.value?.label ?? props.field);
const required = computed(
  () =>
    !!props.f.stage &&
    !!props.f.data?.stages[props.f.stage]?.required.includes(props.field)
);
const wide = computed(
  () =>
    meta.value?.fieldtype === "Table" ||
    meta.value?.fieldtype === "Small Text" ||
    !!choices.value ||
    (props.field === "modules" && props.compact)
);

const choices = computed(() =>
  props.field === "services"
    ? props.f.data?.services
    : props.field === "platforms"
    ? props.f.data?.platforms
    : null
);
const picked = computed(() => splitChoices(props.f.detail(props.field)));
function toggle(choice: string) {
  const next = picked.value.includes(choice)
    ? picked.value.filter((c) => c !== choice)
    : [...picked.value, choice];
  // in the requirements' order, as the server keeps them
  props.f.setDetail(
    props.field,
    (choices.value ?? []).filter((c) => next.includes(c)).join(", ")
  );
}

const moduleRows = computed(
  () => (props.f.detail("modules") as Record<string, unknown>[]) ?? []
);
const moduleNames = computed(() =>
  moduleRows.value.map((r) => String(r.module || ""))
);
// ERPNext's modules, the project's, and any already picked
const moduleChoices = computed(() => [
  ...new Set([
    ...(props.f.data?.erpnext_modules ?? []),
    ...(props.f.data?.project_modules ?? []),
    ...moduleNames.value.filter(Boolean),
  ]),
]);
function toggleModule(module: string) {
  props.f.setDetail(
    "modules",
    moduleNames.value.includes(module)
      ? moduleRows.value.filter((r) => r.module !== module)
      : [
          ...moduleRows.value,
          { module, processes_covered: "", status: "Completed", remarks: "" },
        ]
  );
}

const selectOptions = computed(() =>
  ["", ...(meta.value?.options ?? [])].map((o) => ({
    label: o ? __(o) : "",
    value: o,
  }))
);
const inputType = computed(() => {
  const type = meta.value?.fieldtype;
  if (type === "Date") return "date";
  if (["Int", "Float", "Currency", "Percent"].includes(type ?? ""))
    return "number";
  return props.field.endsWith("_url") ? "url" : "text";
});
const placeholder = computed(() =>
  props.field.endsWith("_url") ? "https://" : undefined
);
</script>
