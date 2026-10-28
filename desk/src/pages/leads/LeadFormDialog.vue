<template>
  <Dialog
    :open="open"
    :title="lead ? __('Edit lead') : __('New lead')"
    size="xl"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <TaskyState
      v-if="leadOptions.error && !options"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the form')"
      :message="
        errorText(leadOptions.error, __('Check your connection and try again.'))
      "
    >
      <Button :label="__('Try again')" @click="leadOptions.reload()" />
    </TaskyState>

    <form
      v-else
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl
          v-model="form.lead_name"
          :label="__('Contact name')"
          maxlength="140"
          required
          autocomplete="off"
        />
        <FormControl
          v-model="form.company_name"
          :label="__('Company')"
          maxlength="140"
          autocomplete="off"
        />
        <FormControl
          v-model="form.email_id"
          type="email"
          :label="__('Email')"
          autocomplete="off"
        />
        <FormControl
          v-model="form.mobile_no"
          type="tel"
          :label="__('Mobile')"
          autocomplete="off"
        />
        <FormControl
          v-model="form.source"
          type="select"
          :label="__('Source')"
          :options="choices(options?.sources, __('Not set'))"
        />
        <FormControl
          v-model="form.segment"
          type="select"
          :label="__('Segment')"
          :options="choices(options?.segments, __('Not set'))"
        />
        <FormControl
          v-model="form.territory"
          type="select"
          :label="__('Territory')"
          :options="choices(options?.territories, __('Not set'))"
        />
        <FormControl
          v-model="form.industry"
          type="select"
          :label="__('Industry')"
          :options="choices(options?.industries, __('Not set'))"
        />
        <FormControl
          v-if="departmentChoices.length"
          v-model="form.tbo_department"
          type="select"
          :label="__('Department')"
          :options="departmentChoices"
        />
        <!-- Combobox layers inside the dialog, so Escape and clicking outside still close it -->
        <Combobox
          :label="__('Owner')"
          :options="ownerOptions"
          :placeholder="__('You, unless you pick someone')"
          :empty-text="__('No one with a sales account')"
          :loading="leadOptions.loading"
          :model-value="form.lead_owner || null"
          @update:model-value="(v: string | null) => (form.lead_owner = v || '')"
        />
        <FormControl
          v-model="form.next_follow_up"
          type="date"
          :label="__('Next follow-up')"
        />
      </div>

      <FormControl
        v-if="!lead"
        v-model="remarks"
        type="textarea"
        :label="__('Remarks')"
        :rows="3"
        :description="__('Saved as the lead\'s first note.')"
      />

      <p v-if="!lead" class="text-p-xs text-ink-gray-6">
        {{
          __("The lead is created in ERPNext on the ERP site, under your name.")
        }}
      </p>

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
          :label="lead ? __('Save changes') : __('Create lead')"
          :loading="saving"
          :disabled="!!leadOptions.error && !options"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, Combobox, call, Dialog, FormControl, toast } from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import {
  choices,
  LEAD_FORM_FIELDS,
  loadLeadOptions,
  leadDepartments,
  leadOptions,
  ownDepartment,
  usableDepartments,
  type LeadDepartment,
  type LeadForm,
  type LeadOptions,
  type LeadRow,
} from "./leads";

const props = defineProps<{
  open: boolean;
  /** the lead to edit; a new lead without it */
  lead?: (LeadRow & Partial<LeadForm>) | null;
}>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  /** `unsavedNote`: remarks on a new lead that didn't save, for the lead page's note box */
  (e: "saved", name: string, unsavedNote?: string): void;
}>();

const formId = `lead-form-${useId()}`;
const options = computed(() => leadOptions.data as LeadOptions | undefined);
const errorMessage = ref("");

function blank(): LeadForm {
  return Object.fromEntries(
    LEAD_FORM_FIELDS.map((field) => [field, ""])
  ) as unknown as LeadForm;
}

const form = reactive<LeadForm>(blank());
// not a lead field: the ERP site's create takes only those, so remarks go in as a note
const remarks = ref("");
// bumped on each open, so a save that finishes after the form was closed and opened
// again leaves that form alone
let opening = 0;

// a fresh form each time it opens: the lead's values, or empty
watch(
  () => props.open,
  (open) => {
    if (!open) return;
    opening++;
    errorMessage.value = "";
    remarks.value = "";
    const values = blank();
    for (const field of LEAD_FORM_FIELDS) {
      values[field] = String(props.lead?.[field] ?? "");
    }
    Object.assign(form, values);
    loadLeadOptions();
    if (options.value?.departments?.length && !leadDepartments.loading)
      leadDepartments.fetch();
    startInOwnDepartment();
  },
  { immediate: true }
);

const departmentChoices = computed(() => {
  const list = usableDepartments(options.value, form.tbo_department).map(
    (d) => ({
      label: d.lead_type ? `${d.name} · ${d.lead_type}` : d.name,
      value: d.name,
    })
  );
  return list.length ? [{ label: __("Not set"), value: "" }, ...list] : [];
});

// a new lead starts in the person's only department, once the options are there
function startInOwnDepartment() {
  if (props.open && !props.lead && !form.tbo_department)
    form.tbo_department = ownDepartment(options.value);
}
watch(options, startInOwnDepartment);

/** The picked department's heads and members: who the owner picker puts first. */
const departmentPeople = computed(() => {
  const department = (
    leadDepartments.data?.departments as LeadDepartment[] | undefined
  )?.find((d) => d.name === form.tbo_department);
  return new Set(
    [...(department?.heads ?? []), ...(department?.members ?? [])].map(
      (p) => p.user
    )
  );
});

const ownerOptions = computed(() => {
  const owners = (options.value?.owners ?? []).map((o) => ({
    label: o.full_name || o.email,
    value: o.email,
    description: o.full_name ? o.email : undefined,
  }));
  if (!departmentPeople.value.size) return owners;
  const inDepartment = owners.filter((o) =>
    departmentPeople.value.has(o.value)
  );
  if (!inDepartment.length) return owners;
  return [
    { group: __("In {0}", form.tbo_department), items: inDepartment },
    {
      group: __("Everyone else"),
      items: owners.filter((o) => !departmentPeople.value.has(o.value)),
    },
  ];
});

/** Only what changed on an edit; every filled field on a new lead. */
function payload() {
  const data: Partial<LeadForm> = {};
  for (const field of LEAD_FORM_FIELDS) {
    const value = form[field].trim();
    const before = String(props.lead?.[field] ?? "");
    if (props.lead ? value !== before : value) data[field] = value;
  }
  return data;
}

function validate() {
  if (!form.lead_name.trim()) return __("Give the contact's name.");
  if (form.email_id.trim() && !/^\S+@\S+\.\S+$/.test(form.email_id.trim()))
    return __("Check the email address; it looks incomplete.");
  return "";
}

const saving = ref(false);

function submit() {
  if (saving.value) return;
  errorMessage.value = validate();
  if (errorMessage.value) return;
  const data = payload();
  if (props.lead && !Object.keys(data).length) {
    emit("update:open", false);
    return;
  }
  // create or update is decided now, from the lead the dialog has at this moment
  const lead = props.lead;
  const note = lead ? "" : remarks.value.trim();
  const opened = opening;
  saving.value = true;
  call(
    lead ? "helpdesk.api.leads.update_lead" : "helpdesk.api.leads.create_lead",
    lead ? { name: lead.name, data } : { data }
  )
    .then(async (result: { name?: string } | null) => {
      let unsavedNote = "";
      if (note && result?.name) {
        // the lead exists now, so a failed note mustn't send the person back to create it again
        await call("helpdesk.api.leads.add_note", {
          name: result.name,
          note,
        }).catch(() => {
          unsavedNote = note;
          toast.warning(
            __(
              "The remarks weren't saved. They're in the lead's note box to add again."
            )
          );
        });
      }
      toast.success(lead ? __("Lead saved") : __("Lead created"));
      if (opened !== opening) return;
      emit("saved", result?.name || lead?.name || "", unsavedNote || undefined);
      emit("update:open", false);
    })
    .catch((e: unknown) => {
      if (opened !== opening) return;
      errorMessage.value = errorText(
        e,
        __("Couldn't save the lead. Check your connection and try again.")
      );
    })
    .finally(() => (saving.value = false));
}
</script>
