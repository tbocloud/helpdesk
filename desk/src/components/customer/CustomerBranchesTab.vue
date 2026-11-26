<template>
  <div>
    <div class="flex items-center justify-between gap-3 pb-4">
      <div class="min-w-0">
        <h2 class="text-lg-semibold text-ink-gray-9">{{ __("Branches") }}</h2>
        <p class="mt-0.5 text-p-sm text-ink-gray-6">
          {{
            __(
              "Each branch gets its own content plan, approvers and Meta page in the Content Calendar."
            )
          }}
        </p>
      </div>
      <Button
        v-if="branches.data?.can_edit"
        :label="__('Add branch')"
        variant="subtle"
        @click="edit(null)"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>

    <div
      v-if="branches.loading && !branches.data"
      class="overflow-hidden rounded-lg border border-outline-gray-2"
      :aria-label="__('Loading')"
    >
      <div
        v-for="i in 3"
        :key="i"
        class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
      >
        <span class="h-3.5 w-1/4 animate-pulse rounded bg-surface-gray-2" />
        <span class="h-3 w-2/5 animate-pulse rounded bg-surface-gray-2" />
      </div>
    </div>

    <TaskyState
      v-else-if="branches.error && !branches.data"
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the branches')"
      :message="errorText(branches.error, __('Try again.'))"
      error
    >
      <Button :label="__('Retry')" @click="branches.reload()" />
    </TaskyState>

    <TaskyState
      v-else-if="!rows.length"
      :icon="LucideStore"
      :title="__('No branches')"
      :message="
        __(
          'Add branches when this customer has several shops or offices that each post, approve and plan on their own.'
        )
      "
    >
      <Button
        v-if="branches.data?.can_edit"
        :label="__('Add branch')"
        @click="edit(null)"
      />
    </TaskyState>

    <ul
      v-else
      role="list"
      class="overflow-hidden rounded-lg border border-outline-gray-2"
    >
      <li
        v-for="branch in rows"
        :key="branch.name"
        class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
      >
        <span class="min-w-0">
          <span class="flex items-center gap-2">
            <span class="truncate text-sm text-ink-gray-9">
              {{ branch.branch_name }}
            </span>
            <TaskyBadge
              v-if="!branch.enabled"
              :label="__('Disabled')"
              tone="neutral"
            />
          </span>
          <span
            class="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-ink-gray-6"
          >
            <span class="truncate">
              {{
                branch.project
                  ? __("Project: {0}", branch.project_name || branch.project)
                  : __("Uses the customer's project")
              }}
            </span>
            <span aria-hidden="true">·</span>
            <span class="truncate">
              {{
                branch.approvers.length
                  ? __("Approvers: {0}", branch.approvers.join(", "))
                  : __("Approved by the customer's contacts")
              }}
            </span>
            <template v-if="!branch.has_plan">
              <span aria-hidden="true">·</span>
              <span>{{ __("No monthly plan") }}</span>
            </template>
          </span>
        </span>
        <Button
          v-if="branches.data?.can_edit"
          size="sm"
          variant="ghost"
          :aria-label="__('Edit {0}', branch.branch_name)"
          @click="edit(branch)"
        >
          <LucidePencil class="size-4" aria-hidden="true" />
        </Button>
      </li>
    </ul>

    <Dialog
      v-model:open="dialogOpen"
      :options="{ title: editing ? __('Edit branch') : __('Add branch') }"
    >
      <template #body-content>
        <form
          id="branch-form"
          class="flex flex-col gap-4"
          novalidate
          @submit.prevent="save"
        >
          <FormControl
            v-model="form.branch_name"
            :label="__('Branch name') + ' *'"
            :placeholder="__('e.g. Kochi')"
            :disabled="!!editing"
            maxlength="140"
            required
          />
          <Link
            v-model="form.project"
            doctype="Project"
            :label="__('Project')"
            :placeholder="__('The customer\'s project')"
          />
          <p class="-mt-2 text-p-xs text-ink-gray-6">
            {{
              __(
                "The branch's post tasks go to this project, and its posts publish to the Meta page connected to it. Leave empty to use the customer's."
              )
            }}
          </p>
          <FormControl
            v-model="form.approvers"
            type="textarea"
            :label="__('Approvers')"
            :placeholder="__('manager.kochi@company.com')"
            :description="
              __(
                'One email per line. They see only this branch\'s posts in the client portal and get its reminders. Leave empty for the customer\'s contacts.'
              )
            "
            :rows="3"
          />
          <FormControl
            v-model="form.enabled"
            type="checkbox"
            :label="__('Enabled')"
          />
          <p v-if="error" class="text-p-sm text-danger" role="alert">
            {{ error }}
          </p>
        </form>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="dialogOpen = false" />
          <Button
            variant="solid"
            type="submit"
            form="branch-form"
            :label="__('Save')"
            :loading="saving"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { useCustomerBranches } from "@/pages/content/branches";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, createResource, Dialog, FormControl } from "frappe-ui";
import { computed, reactive, ref } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlus from "~icons/lucide/plus";
import LucideStore from "~icons/lucide/store";

interface BranchRow {
  name: string;
  branch_name: string;
  enabled: 0 | 1;
  project: string | null;
  project_name: string | null;
  approvers: string[];
  has_plan: boolean;
}

const props = defineProps<{ customer: string }>();
const { reload: reloadPickers } = useCustomerBranches();

const branches = createResource({
  url: "helpdesk.api.customer_branches.get_customer_branches",
  makeParams: () => ({ customer: props.customer }),
  auto: true,
});
const rows = computed<BranchRow[]>(() => branches.data?.branches ?? []);

const dialogOpen = ref(false);
const editing = ref<BranchRow | null>(null);
const form = reactive({
  branch_name: "",
  project: "",
  approvers: "",
  enabled: true,
});
const saving = ref(false);
const error = ref("");

function edit(branch: BranchRow | null) {
  editing.value = branch;
  error.value = "";
  Object.assign(form, {
    branch_name: branch?.branch_name ?? "",
    project: branch?.project ?? "",
    approvers: branch?.approvers.join("\n") ?? "",
    enabled: branch ? !!branch.enabled : true,
  });
  dialogOpen.value = true;
}

async function save() {
  if (!form.branch_name.trim()) {
    error.value = __("Give the branch a name.");
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    await call("helpdesk.api.customer_branches.save_branch", {
      customer: props.customer,
      name: editing.value?.name,
      values: {
        branch_name: form.branch_name.trim(),
        project: form.project || null,
        approvers: form.approvers
          .split(/[\s,;]+/)
          .map((e) => e.trim())
          .filter(Boolean),
        enabled: form.enabled ? 1 : 0,
      },
    });
    dialogOpen.value = false;
    branches.reload();
    reloadPickers();
  } catch (e) {
    error.value = errorText(e, __("Couldn't save the branch."));
  } finally {
    saving.value = false;
  }
}
</script>
