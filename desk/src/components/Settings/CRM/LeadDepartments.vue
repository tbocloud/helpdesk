<template>
  <!-- stays out until the ERP site's TBO Smart has departments -->
  <SettingsSection
    v-if="available || error"
    :title="__('Lead departments')"
    :description="
      __(
        'Group leads by department, like GrowthX. Heads see every lead in their department, members see their own. Set the type once; the ERP site enforces who sees what.'
      )
    "
  >
    <template #actions>
      <Button
        v-if="available"
        :label="__('Add department')"
        @click="openDialog(null)"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>

    <div
      v-if="error"
      role="alert"
      class="flex flex-wrap items-center gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
    >
      <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
      <span class="min-w-0 flex-1">{{ error }}</span>
      <Button :label="__('Try again')" @click="reload" />
    </div>
    <div
      v-else-if="!departments.length"
      class="rounded-lg border border-dashed border-outline-gray-3 px-4 py-6 text-center text-p-sm text-ink-gray-6"
    >
      {{
        __(
          "No departments yet. Add one, then pick it on a lead to put the lead there."
        )
      }}
    </div>
    <ul
      v-else
      role="list"
      class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2"
      :aria-busy="loading"
    >
      <li
        v-for="department in departments"
        :key="department.name"
        class="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3"
      >
        <div class="flex min-w-0 flex-1 flex-col gap-0.5">
          <span class="truncate text-base-medium text-ink-gray-9">{{
            department.department_name || department.name
          }}</span>
          <span class="text-p-xs text-ink-gray-6">
            {{ department.lead_type }}
            <template v-if="department.heads.length">
              · {{ __("Heads") }}: {{ people(department.heads) }}
            </template>
            ·
            <span class="tabular-nums">{{
              __("{0} members", String(department.members.length))
            }}</span>
          </span>
        </div>
        <Switch
          :model-value="!!department.is_active"
          :label="department.is_active ? __('Active') : __('Inactive')"
          :disabled="toggling === department.name"
          :aria-label="__('{0} is active', department.name)"
          @update:model-value="setActive(department, $event)"
        />
        <Button
          variant="ghost"
          :label="__('Edit {0}', department.name)"
          @click="openDialog(department)"
        >
          <template #icon>
            <LucidePencil class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </li>
    </ul>
    <div
      v-if="loading && !leadDepartments.data"
      class="h-12 animate-pulse rounded-lg bg-surface-gray-2"
      aria-busy="true"
      :aria-label="__('Loading')"
    />
  </SettingsSection>

  <Dialog
    v-model:open="showDialog"
    :title="editing ? __('Edit department') : __('Add department')"
    size="lg"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="save"
    >
      <FormControl
        v-model="form.department_name"
        :label="__('Name')"
        :disabled="!!editing"
        maxlength="140"
        required
        autocomplete="off"
      />
      <FormControl
        v-model="form.lead_type"
        type="select"
        :label="__('Lead type')"
        :options="typeOptions"
      />
      <div class="flex flex-col gap-1.5">
        <FormLabel :label="__('Heads')" size="md" />
        <MultiSelect
          v-model="form.heads"
          :options="userOptions"
          :loading="agents.loading"
          :placeholder="__('Pick the heads')"
          class="w-full"
        />
        <p class="text-p-xs text-ink-gray-6">
          {{ __("Heads see every lead in the department.") }}
        </p>
      </div>
      <div class="flex flex-col gap-1.5">
        <FormLabel :label="__('Members')" size="md" />
        <MultiSelect
          v-model="form.members"
          :options="userOptions"
          :loading="agents.loading"
          :placeholder="__('Pick the members')"
          class="w-full"
        />
        <p class="text-p-xs text-ink-gray-6">
          {{ __("Members see the leads they own.") }}
        </p>
      </div>
      <Switch v-model="form.is_active" :label="__('Active')" />
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
          :label="editing ? __('Save changes') : __('Add department')"
          :loading="saving"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { useAgentStore } from "@/stores/agent";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  loadLeadOptions,
  leadDepartments,
  leadOptions,
  type LeadDepartment,
  type LeadOptions,
} from "@/pages/leads/leads";
import {
  Button,
  call,
  Dialog,
  FormControl,
  FormLabel,
  MultiSelect,
  Switch,
  toast,
} from "frappe-ui";
import { computed, onMounted, reactive, ref, useId } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlus from "~icons/lucide/plus";
import SettingsSection from "../SettingsSection.vue";

const { agents } = useAgentStore();
const formId = `lead-department-${useId()}`;
// the two types the owner works with, until the ERP site's options say otherwise
const FALLBACK_TYPES = ["ERP / Software", "Content / Digital Marketing"];

const available = computed(() => !!leadDepartments.data?.available);
const departments = computed(
  () => (leadDepartments.data?.departments ?? []) as LeadDepartment[]
);
const loading = computed(() => leadDepartments.loading);
const error = computed(() =>
  leadDepartments.error
    ? errorText(
        leadDepartments.error,
        __("Couldn't load the departments. Check your connection.")
      )
    : ""
);

onMounted(() => {
  leadDepartments.fetch();
  loadLeadOptions();
  if (!agents.loading && !agents.data?.length && !agents.list.promise)
    agents.fetch();
});

function reload() {
  leadDepartments.submit({ fresh: 1 });
}

function people(list: { user: string; full_name?: string }[]) {
  return list.map((p) => p.full_name || p.user).join(", ");
}

const typeOptions = computed(() => {
  const types =
    (leadOptions.data as LeadOptions | undefined)?.lead_types ?? FALLBACK_TYPES;
  return types.map((t) => ({ label: t, value: t }));
});

/** The hub's agents by their email, which is how the ERP site knows them; a person a
 * department already has stays pickable even when they are no longer an active agent. */
const userOptions = computed(() => {
  const options = new Map<string, { label: string; value: string }>();
  for (const a of agents.data ?? [])
    if (a.user)
      options.set(a.user, {
        label: a.agent_name ? `${a.agent_name} (${a.user})` : a.user,
        value: a.user,
      });
  for (const d of departments.value)
    for (const p of [...d.heads, ...d.members])
      if (!options.has(p.user))
        options.set(p.user, {
          label: p.full_name ? `${p.full_name} (${p.user})` : p.user,
          value: p.user,
        });
  return [...options.values()];
});

interface DepartmentForm {
  department_name: string;
  lead_type: string;
  is_active: boolean;
  heads: string[];
  members: string[];
}

const showDialog = ref(false);
const editing = ref<LeadDepartment | null>(null);
const errorMessage = ref("");
const saving = ref(false);
const form = reactive<DepartmentForm>({
  department_name: "",
  lead_type: "",
  is_active: true,
  heads: [],
  members: [],
});

function openDialog(department: LeadDepartment | null) {
  editing.value = department;
  errorMessage.value = "";
  Object.assign(form, {
    department_name: department?.department_name ?? "",
    lead_type: department?.lead_type || typeOptions.value[0]?.value || "",
    is_active: department ? !!department.is_active : true,
    heads: department?.heads.map((p) => p.user) ?? [],
    members: department?.members.map((p) => p.user) ?? [],
  });
  showDialog.value = true;
}

function save() {
  if (saving.value) return;
  if (!form.department_name.trim()) {
    errorMessage.value = __("Give the department a name.");
    return;
  }
  errorMessage.value = "";
  saving.value = true;
  call("helpdesk.api.leads.save_lead_department", {
    name: editing.value?.name ?? null,
    values: {
      ...form,
      department_name: form.department_name.trim(),
      is_active: form.is_active ? 1 : 0,
    },
  })
    .then(() => {
      toast.success(
        editing.value ? __("Department saved") : __("Department added")
      );
      showDialog.value = false;
      refreshAfterChange();
    })
    // the ERP site's own reason, e.g. only System Managers and Sales Managers may
    .catch((e: unknown) => {
      errorMessage.value = errorText(
        e,
        __("Couldn't save the department. Check your connection and try again.")
      );
    })
    .finally(() => (saving.value = false));
}

const toggling = ref("");

function setActive(department: LeadDepartment, active: boolean) {
  toggling.value = department.name;
  call("helpdesk.api.leads.set_lead_department_active", {
    name: department.name,
    active: active ? 1 : 0,
  })
    .then(refreshAfterChange)
    .catch((e: unknown) => {
      toast.error(errorText(e, __("Couldn't change the department.")));
      // the switch follows the list, which still has the old value
      reload();
    })
    .finally(() => (toggling.value = ""));
}

/** The lists the Leads page filters by are read again, not served from the cache. */
function refreshAfterChange() {
  reload();
  leadOptions.submit({ fresh: 1 });
}
</script>
