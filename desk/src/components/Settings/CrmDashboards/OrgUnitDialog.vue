<template>
  <Dialog v-model:open="open" :title="title" size="lg">
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="save"
    >
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl
          v-model="form.unit_name"
          :label="__('Name on the leads')"
          :description="
            unit
              ? __('Fixed once saved.')
              : __('Exactly as the leads carry it, if they do.')
          "
          :disabled="!!unit"
          maxlength="140"
          required
          autocomplete="off"
        />
        <FormControl
          v-model="form.label"
          :label="__('Display name')"
          :placeholder="form.unit_name"
          maxlength="140"
          autocomplete="off"
        />
      </div>

      <div v-if="parents.length" class="flex flex-col gap-2">
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "Where it sits. Pick the closest one; the ones above it fill in from it."
            )
          }}
        </p>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormControl
            v-for="level in parents"
            :key="level"
            v-model="form[level]"
            type="select"
            :label="levelLabel(level)"
            :options="parentOptions(level)"
          />
        </div>
      </div>

      <div v-if="type === 'Employee'" class="flex flex-col gap-1.5">
        <FormLabel :label="__('User')" size="md" />
        <Link
          v-model="form.user"
          doctype="User"
          :placeholder="__('Pick their user')"
        />
        <p class="text-p-xs text-ink-gray-6">
          {{ __("So a dashboard can show them their own part.") }}
        </p>
      </div>
      <div v-if="type === 'Team'" class="flex flex-col gap-1.5">
        <FormLabel :label="__('Team leader')" size="md" />
        <Link
          v-model="form.leader"
          doctype="User"
          :placeholder="__('Pick the leader')"
        />
        <p class="text-p-xs text-ink-gray-6">
          {{ __("A team leader's dashboard shows the teams they lead.") }}
        </p>
      </div>

      <Switch
        v-model="form.is_active"
        :label="__('Active')"
        :description="__('An inactive unit\'s leads count on no dashboard.')"
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
      <div class="flex flex-wrap items-center justify-between gap-2">
        <Button
          v-if="canDelete"
          variant="ghost"
          theme="red"
          :label="__('Delete')"
          :loading="deleting"
          @click="remove"
        />
        <span v-else />
        <div class="flex gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            type="submit"
            :form="formId"
            :label="unit ? __('Save changes') : addLabel"
            :loading="saving"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  Dialog,
  FormControl,
  FormLabel,
  Switch,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import { LEVELS, unitTypeLabel, type OrgUnit } from "./crmDashboards";

const props = defineProps<{
  unit: OrgUnit | null;
  unitType: string;
  source: string;
  /** every unit of the source, for the parent pickers */
  units: OrgUnit[];
  /** each unit type's possible parents (the registry's unit_parents) */
  unitParents: Record<string, string[]>;
}>();
const emit = defineEmits<{ saved: [] }>();
const open = defineModel<boolean>("open", { required: true });

const API = "helpdesk.api.crm_dashboard_settings";

const formId = `crm-unit-${useId()}`;
const form = reactive<Record<string, any>>({});
const error = ref("");
const saving = ref(false);
const deleting = ref(false);

const type = computed(() => props.unit?.unit_type || props.unitType);
const parents = computed(() => props.unitParents[type.value] || []);
const title = computed(() =>
  props.unit
    ? __("Edit {0}", props.unit.label)
    : __("Add {0}", unitTypeLabel(type.value).toLowerCase())
);
const addLabel = computed(() =>
  __("Add {0}", unitTypeLabel(type.value).toLowerCase())
);
// a synced unit would come back at the next sync; switch it off instead
const canDelete = computed(
  () => !!props.unit && props.unit.origin === "Added here" && !props.unit.leads
);

watch(open, (isOpen) => {
  if (!isOpen) return;
  const unit = props.unit;
  Object.assign(form, {
    unit_name: unit?.unit_name || "",
    label: unit && unit.label !== unit.unit_name ? unit.label : "",
    company: unit?.company || "",
    branch: unit?.branch || "",
    department: unit?.department || "",
    team: unit?.team || "",
    user: unit?.user || "",
    leader: unit?.leader || "",
    is_active: unit ? !!unit.is_active : true,
  });
  error.value = "";
});

function levelLabel(level: string) {
  const entry = LEVELS.find(([key]) => key === level);
  return entry ? unitTypeLabel(entry[1]) : level;
}

function parentOptions(level: string) {
  const entry = LEVELS.find(([key]) => key === level);
  return [
    { label: __("None"), value: "" },
    ...props.units
      .filter((u) => u.unit_type === entry?.[1])
      .map((u) => ({ label: u.label, value: u.unit_name })),
  ];
}

async function save() {
  if (!form.unit_name.trim() || saving.value) {
    error.value = form.unit_name.trim()
      ? ""
      : __("Type its name on the leads.");
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    const values: Record<string, unknown> = {
      source: props.source,
      unit_type: type.value,
      unit_name: form.unit_name.trim(),
      label: form.label.trim() || form.unit_name.trim(),
      is_active: form.is_active ? 1 : 0,
    };
    for (const level of parents.value) values[level] = form[level];
    if (type.value === "Employee") values.user = form.user || null;
    if (type.value === "Team") values.leader = form.leader || null;
    await call(`${API}.save_unit`, { values, name: props.unit?.name || null });
    toast.success(props.unit ? __("Saved") : __("Added"));
    open.value = false;
    emit("saved");
  } catch (e) {
    error.value = errorText(e, __("Couldn't save it. Try again."));
  } finally {
    saving.value = false;
  }
}

async function remove() {
  deleting.value = true;
  try {
    await call(`${API}.delete_unit`, { name: props.unit!.name });
    toast.success(__("Deleted"));
    open.value = false;
    emit("saved");
  } catch (e) {
    error.value = errorText(e, __("Couldn't delete it. Try again."));
  } finally {
    deleting.value = false;
  }
}
</script>
