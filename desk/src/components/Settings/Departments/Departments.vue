<template>
  <SettingsLayoutBase
    :title="__('Departments')"
    :description="
      __(
        'The Projects page groups projects by department, in this order. Inactive departments can\'t be picked for projects.'
      )
    "
  >
    <template #content>
      <form class="flex items-end gap-2" @submit.prevent="addDepartment">
        <TextInput
          v-model="newName"
          class="min-w-0 flex-1"
          :placeholder="__('e.g. Creative')"
          :aria-label="__('New department name')"
          maxlength="140"
        />
        <Button
          variant="solid"
          type="submit"
          :label="__('Add department')"
          :loading="add.loading"
          :disabled="!newName.trim()"
        >
          <template #prefix
            ><LucidePlus class="size-4" aria-hidden="true"
          /></template>
        </Button>
      </form>

      <div
        v-if="departments.loading && !departments.data"
        class="flex justify-center py-10"
      >
        <LoadingIndicator class="w-4" />
      </div>
      <div
        v-else-if="departments.error"
        role="alert"
        class="mt-6 flex items-center gap-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
        {{ __("Couldn't load departments.") }}
        <Button :label="__('Retry')" @click="departments.reload()" />
      </div>
      <p v-else-if="!list.length" class="mt-6 text-p-sm text-ink-gray-6">
        {{ __("No departments yet. Add the first one above.") }}
      </p>
      <ol
        v-else
        class="mt-6 divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2"
        :aria-label="__('Departments in display order')"
      >
        <li
          v-for="(dept, idx) in list"
          :key="dept.name"
          class="flex min-h-12 items-center gap-3 px-3 py-2"
        >
          <span
            class="w-5 shrink-0 text-right font-mono text-xs tabular-nums text-ink-gray-5"
            aria-hidden="true"
            >{{ idx + 1 }}</span
          >

          <!-- rename -->
          <form
            v-if="renaming === dept.name"
            class="flex min-w-0 flex-1 items-center gap-2"
            @submit.prevent="saveRename(dept)"
            @keydown.esc.stop="renaming = ''"
          >
            <TextInput
              :id="RENAME_INPUT_ID"
              v-model="renameValue"
              class="min-w-0 flex-1"
              :aria-label="__('New name for {0}', dept.name)"
              maxlength="140"
            />
            <Button
              variant="solid"
              type="submit"
              :label="__('Save')"
              :loading="rename.loading"
              :disabled="!renameValue.trim()"
            />
            <Button :label="__('Cancel')" @click="renaming = ''" />
          </form>

          <!-- delete confirmation -->
          <div
            v-else-if="deleting === dept.name"
            class="flex min-w-0 flex-1 flex-wrap items-center gap-2"
            role="group"
            :aria-label="__('Confirm deleting {0}', dept.name)"
          >
            <span class="min-w-0 flex-1 text-p-sm text-ink-gray-8">
              {{ __("Delete {0}?", dept.name) }}
            </span>
            <Button :label="__('Cancel')" @click="deleting = ''" />
            <Button
              theme="red"
              variant="solid"
              :label="__('Delete')"
              :loading="remove.loading"
              @click="remove.submit({ department: dept.name })"
            />
          </div>

          <template v-else>
            <div class="flex min-w-0 flex-1 flex-col">
              <span class="flex min-w-0 items-center gap-2">
                <span
                  class="truncate text-base-medium"
                  :class="
                    dept.is_active ? 'text-ink-gray-9' : 'text-ink-gray-5'
                  "
                  >{{ dept.name }}</span
                >
                <span
                  v-if="!dept.is_active"
                  class="shrink-0 rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-6"
                  >{{ __("Inactive") }}</span
                >
              </span>
              <span class="text-xs tabular-nums text-ink-gray-5">
                {{
                  dept.project_count === 1
                    ? __("1 project")
                    : __("{0} projects", String(dept.project_count))
                }}
              </span>
            </div>

            <div class="flex shrink-0 items-center gap-0.5">
              <Button
                variant="ghost"
                :tooltip="__('Move up')"
                :label="__('Move {0} up', dept.name)"
                :disabled="idx === 0 || move.loading"
                @click="move.submit({ department: dept.name, direction: 'up' })"
              >
                <template #icon
                  ><LucideArrowUp class="size-4" aria-hidden="true"
                /></template>
              </Button>
              <Button
                variant="ghost"
                :tooltip="__('Move down')"
                :label="__('Move {0} down', dept.name)"
                :disabled="idx === list.length - 1 || move.loading"
                @click="
                  move.submit({ department: dept.name, direction: 'down' })
                "
              >
                <template #icon
                  ><LucideArrowDown class="size-4" aria-hidden="true"
                /></template>
              </Button>
              <Button
                variant="ghost"
                :tooltip="__('Rename')"
                :label="__('Rename {0}', dept.name)"
                @click="startRename(dept)"
              >
                <template #icon
                  ><LucidePencil class="size-4" aria-hidden="true"
                /></template>
              </Button>
              <Button
                variant="ghost"
                :tooltip="dept.is_active ? __('Deactivate') : __('Activate')"
                :label="
                  dept.is_active
                    ? __('Deactivate {0}', dept.name)
                    : __('Activate {0}', dept.name)
                "
                :loading="toggling === dept.name"
                @click="toggleActive(dept)"
              >
                <template #icon>
                  <component
                    :is="dept.is_active ? LucideEyeOff : LucideEye"
                    class="size-4"
                    aria-hidden="true"
                  />
                </template>
              </Button>
              <Button
                variant="ghost"
                :tooltip="__('Delete')"
                :label="__('Delete {0}', dept.name)"
                @click="deleting = dept.name"
              >
                <template #icon
                  ><LucideTrash2 class="size-4" aria-hidden="true"
                /></template>
              </Button>
            </div>
          </template>
        </li>
      </ol>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { __ } from "@/translation";
import {
  Button,
  createResource,
  LoadingIndicator,
  TextInput,
  toast,
} from "frappe-ui";
import { computed, nextTick, ref } from "vue";
import LucideArrowDown from "~icons/lucide/arrow-down";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideEye from "~icons/lucide/eye";
import LucideEyeOff from "~icons/lucide/eye-off";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";

interface Department {
  name: string;
  department_name: string;
  sort_order: number;
  is_active: boolean;
  description?: string;
  project_count: number;
}

const API = "helpdesk.api.departments";

const departments = createResource({
  url: `${API}.get_departments`,
  params: { include_inactive: true },
  auto: true,
  transform: (d: Department[]) => d ?? [],
});
const list = computed<Department[]>(() => departments.data ?? []);

function showError(e: { messages?: string[]; message?: string }) {
  toast.error(
    e?.messages?.[0] || e?.message || __("Something went wrong. Try again.")
  );
}

// --- add ---

const newName = ref("");
const add = createResource({
  url: `${API}.add_department`,
  onSuccess() {
    toast.success(__("Department added"));
    newName.value = "";
    departments.reload();
  },
  onError: showError,
});

function addDepartment() {
  const name = newName.value.trim();
  if (!name || add.loading) return;
  add.submit({ department_name: name });
}

// --- rename ---

const RENAME_INPUT_ID = "department-rename-input";
const renaming = ref("");
const renameValue = ref("");

async function startRename(dept: Department) {
  deleting.value = "";
  renaming.value = dept.name;
  renameValue.value = dept.name;
  await nextTick();
  (
    document.getElementById(RENAME_INPUT_ID) as HTMLInputElement | null
  )?.select();
}

const rename = createResource({
  url: `${API}.rename_department`,
  onSuccess() {
    toast.success(__("Department renamed"));
    renaming.value = "";
    departments.reload();
  },
  onError: showError,
});

function saveRename(dept: Department) {
  const name = renameValue.value.trim();
  if (!name || rename.loading) return;
  if (name === dept.name) {
    renaming.value = "";
    return;
  }
  rename.submit({ department: dept.name, new_name: name });
}

// --- reorder, activate, delete ---

const move = createResource({
  url: `${API}.move_department`,
  onSuccess: () => departments.reload(),
  onError: showError,
});

const toggling = ref("");
const toggle = createResource({
  url: `${API}.set_department_active`,
  onSuccess(data: { is_active: boolean }) {
    toast.success(
      data.is_active ? __("Department activated") : __("Department deactivated")
    );
    departments.reload();
  },
  onError: showError,
});

async function toggleActive(dept: Department) {
  toggling.value = dept.name;
  try {
    await toggle.submit({ department: dept.name, is_active: !dept.is_active });
  } catch {
    // onError has already told the user
  } finally {
    toggling.value = "";
  }
}

const deleting = ref("");
const remove = createResource({
  url: `${API}.delete_department`,
  onSuccess() {
    toast.success(__("Department deleted"));
    deleting.value = "";
    departments.reload();
  },
  onError(e: { messages?: string[]; message?: string }) {
    deleting.value = "";
    showError(e);
  },
});
</script>
