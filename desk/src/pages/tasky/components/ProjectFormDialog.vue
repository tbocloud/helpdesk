<template>
  <!-- the customer picker's dropdown renders outside the dialog, so an
       outside click must not close it; Cancel and the close button still do -->
  <Dialog
    v-model:open="open"
    :title="isEdit ? __('Edit project') : __('New project')"
    size="xl"
    :dismissible="false"
  >
    <div v-if="detail.loading" class="flex flex-col gap-3 py-2">
      <div
        v-for="i in 4"
        :key="i"
        class="h-8 animate-pulse rounded bg-surface-gray-2"
      />
    </div>
    <form
      v-else
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <TextInput
        v-model="form.project_name"
        :label="__('Project name')"
        :placeholder="__('e.g. Acme ERP rollout')"
        required
      />
      <Link
        v-model="form.customer"
        doctype="HD Customer"
        :label="__('Customer')"
        :placeholder="__('Select customer')"
      />
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl
          v-model="form.department"
          type="select"
          :label="__('Department')"
          :options="departmentOptions"
          :description="__('Projects are grouped by department.')"
        />
        <FormControl
          v-model="form.project_type"
          type="select"
          :label="__('Project type')"
          :options="projectTypeOptions"
          :description="
            __('The AI uses this to estimate how long new tasks take.')
          "
        />
      </div>
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <TextInput
          v-model="form.expected_start_date"
          type="date"
          :label="__('Start date')"
          required
        />
        <TextInput
          v-model="form.expected_end_date"
          type="date"
          :label="__('End date')"
          :min="form.expected_start_date || undefined"
          required
        />
        <template v-if="isEdit">
          <FormControl
            v-model="form.status"
            type="select"
            :label="__('Status')"
            :options="STATUSES"
          />
          <FormControl
            v-model="form.priority"
            type="select"
            :label="__('Priority')"
            :options="PRIORITIES"
          />
        </template>
      </div>

      <fieldset class="flex flex-col gap-2">
        <legend class="mb-1.5 text-base text-ink-gray-5">
          {{ __("Team members") }}
        </legend>
        <p v-if="!form.members.length" class="text-p-xs text-ink-gray-5">
          {{
            __(
              "Add the people who will work on this project so tasks can be assigned to them."
            )
          }}
        </p>
        <div
          v-for="(member, idx) in form.members"
          :key="idx"
          class="flex items-center gap-2"
        >
          <FormControl
            v-model="member.user"
            type="select"
            class="min-w-0 flex-1"
            :placeholder="__('Select user…')"
            :options="userOptions"
            :aria-label="__('Member {0}', String(idx + 1))"
          />
          <FormControl
            v-model="member.custom_role"
            type="select"
            class="!w-56 shrink-0"
            :options="roleOptions"
            :aria-label="__('Role for member {0}', String(idx + 1))"
          />
          <Button
            variant="ghost"
            :label="__('Remove member')"
            @click="removeMember(idx)"
          >
            <template #icon><LucideX class="size-4" /></template>
          </Button>
        </div>
        <div>
          <Button
            variant="subtle"
            :label="__('Add member')"
            @click="form.members.push({ user: '', custom_role: 'Developer' })"
          >
            <template #prefix
              ><LucideUserPlus class="size-4" aria-hidden="true"
            /></template>
          </Button>
        </div>
      </fieldset>

      <FormControl
        v-model="form.project_lead"
        type="select"
        :label="__('Project lead')"
        :options="leadOptions"
        :description="
          __(
            'Can create and assign tasks in this project. You can rotate it from the project page.'
          )
        "
      />

      <FormControl
        v-model="form.review_before_done"
        type="checkbox"
        :label="__('Review before done')"
        :description="
          __(
            'Team members\' completed tasks go to the project lead for approval.'
          )
        "
      />

      <div
        v-if="error"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{ error }}
      </div>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="isEdit ? __('Save changes') : __('Create project')"
          :loading="saving"
          :disabled="!canSubmit || detail.loading"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import { __ } from "@/translation";
import {
  Button,
  call,
  createResource,
  Dialog,
  FormControl,
  TextInput,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideUserPlus from "~icons/lucide/user-plus";
import LucideX from "~icons/lucide/x";
import { PROJECT_ROLES } from "../taskMeta";

const props = defineProps<{
  /** Set to edit an existing project; leave empty to create one. */
  projectId?: string;
  /** Department a new project starts in, e.g. the one the Projects page is showing. */
  defaultDepartment?: string;
}>();
const open = defineModel<boolean>("open", { default: false });
const emit = defineEmits<{ saved: [name: string] }>();

const STATUSES = ["Open", "On hold", "Completed", "Cancelled"];
const PRIORITIES = ["Low", "Medium", "High"];

const isEdit = computed(() => !!props.projectId);
const formId = `tasky-project-form-${Math.random().toString(36).slice(2, 8)}`;

const EMPTY = () => ({
  project_name: "",
  customer: "",
  project_type: "",
  department: "",
  expected_start_date: "",
  expected_end_date: "",
  status: "Open",
  priority: "Medium",
  project_lead: "",
  review_before_done: false,
  members: [] as { user: string; custom_role: string }[],
});
const form = reactive(EMPTY());
const saving = ref(false);
const error = ref("");

const userList = createResource({
  url: "helpdesk.tasky.api.get_users",
  auto: true,
  transform: (d: any[]) => d ?? [],
});

const userOptions = computed(() =>
  (userList.data ?? []).map((u: any) => ({
    label: u.full_name || u.name,
    value: u.name,
  }))
);

const projectTypeOptions = computed(() => [
  { label: __("Not set"), value: "" },
  { label: __("ERP Implementation"), value: "ERP Implementation" },
  { label: __("Mobile App"), value: "Mobile App" },
  { label: __("Website"), value: "Website" },
  { label: __("Content Calendar"), value: "Content Calendar" },
  { label: __("Support"), value: "Support" },
  { label: __("Other"), value: "Other" },
]);

const roleOptions = computed(() => [
  ...PROJECT_ROLES.map((role) => ({ label: __(role), value: role })),
  { label: __("Member"), value: "" },
]);

interface Department {
  name: string;
  is_active: boolean;
}

const departments = createResource({
  url: "helpdesk.api.departments.get_departments",
  params: { include_inactive: true },
  transform: (d: Department[]) => d ?? [],
});

// an inactive department stays listed for the project that already has it
const departmentOptions = computed(() => [
  { label: __("No department"), value: "" },
  ...(departments.data ?? [])
    .filter((d: Department) => d.is_active || d.name === form.department)
    .map((d: Department) => ({
      label: d.is_active ? d.name : __("{0} (inactive)", d.name),
      value: d.name,
    })),
]);

const leadOptions = computed(() => [
  { label: __("No lead yet"), value: "" },
  ...form.members
    .filter((m) => m.user)
    .map((m) => ({
      label: userOptions.value.find((o) => o.value === m.user)?.label || m.user,
      value: m.user,
    })),
]);

const detail = createResource({
  url: "helpdesk.tasky.api.get_project_detail",
  makeParams: () => ({ project: props.projectId }),
  onSuccess(data: any) {
    Object.assign(form, EMPTY(), {
      project_name: data.project_name || "",
      customer: data.customer || "",
      project_type: data.project_type || "",
      department: data.department || "",
      expected_start_date: data.expected_start_date || "",
      expected_end_date: data.expected_end_date || "",
      status: data.status || "Open",
      priority: data.priority || "Medium",
      project_lead: data.project_lead || "",
      review_before_done: !!data.review_before_done,
      members: (data.users ?? []).map((u: any) => ({
        user: u.user,
        custom_role: u.role || "",
      })),
    });
  },
});

watch(open, (isOpen) => {
  if (!isOpen) return;
  error.value = "";
  departments.reload();
  if (isEdit.value) detail.reload();
  else
    Object.assign(form, EMPTY(), { department: props.defaultDepartment || "" });
});

const canSubmit = computed(
  () =>
    !!form.project_name.trim() &&
    !!form.expected_start_date &&
    !!form.expected_end_date
);

function removeMember(idx: number) {
  const [removed] = form.members.splice(idx, 1);
  if (removed?.user === form.project_lead) form.project_lead = "";
}

async function submit() {
  if (saving.value) return;
  error.value = "";
  if (!canSubmit.value) {
    error.value = __("Add a project name, start date and end date.");
    return;
  }
  if (form.expected_end_date < form.expected_start_date) {
    error.value = __("The end date can't be before the start date.");
    return;
  }
  saving.value = true;
  const members = JSON.stringify(form.members.filter((m) => m.user.trim()));
  try {
    const res = isEdit.value
      ? await call("helpdesk.tasky.api.update_project", {
          project: props.projectId,
          ...form,
          project_name: form.project_name.trim(),
          project_lead: form.project_lead || null,
          members,
        })
      : await call("helpdesk.tasky.api.create_project", {
          project_name: form.project_name.trim(),
          expected_start_date: form.expected_start_date,
          expected_end_date: form.expected_end_date,
          customer: form.customer,
          project_type: form.project_type,
          department: form.department,
          project_lead: form.project_lead || null,
          members,
          review_before_done: form.review_before_done,
        });
    toast.success(isEdit.value ? __("Project updated") : __("Project created"));
    open.value = false;
    emit("saved", res?.name);
  } catch (e: any) {
    error.value =
      e?.messages?.join(" ") || e?.message || __("Something went wrong.");
  } finally {
    saving.value = false;
  }
}
</script>
