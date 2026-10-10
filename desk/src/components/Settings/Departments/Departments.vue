<template>
  <SettingsLayoutBase
    :title="__('Departments')"
    :description="
      __(
        'The Projects page groups projects by department, in this order. Inactive departments can\'t be picked for projects. Heads are told who their department\'s Scoreboard champion is.'
      )
    "
  >
    <template #content>
      <form class="flex items-end gap-2" @submit.prevent="addDepartment">
        <TextInput
          v-model="newName"
          class="min-w-0 flex-1"
          :label="__('New department')"
          :placeholder="__('e.g. Creative')"
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

      <div class="mt-6">
        <SettingsList
          :items="list"
          :label="__('Departments in display order')"
          :loading="departments.loading"
          :error="departments.error"
          :empty-icon="LucideBuilding2"
          :empty-title="__('No departments yet')"
          :empty-message="
            __('Add the first one above; projects can then be filed under it.')
          "
          @retry="departments.reload()"
        >
          <template #default="{ item: dept, index: idx }">
            <div class="flex min-h-14 items-center gap-3 px-3 py-2">
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
                  :label="__('Rename')"
                  :loading="rename.loading"
                  :disabled="!renameValue.trim()"
                />
                <Button :label="__('Cancel')" @click="renaming = ''" />
              </form>

              <!-- heads -->
              <form
                v-else-if="editingHeads === dept.name"
                class="flex min-w-0 flex-1 flex-col gap-2"
                :aria-label="__('Heads of {0}', dept.name)"
                @submit.prevent="saveHeads(dept)"
                @keydown.esc.stop="editingHeads = ''"
              >
                <span class="text-base-medium text-ink-gray-9">{{
                  __("Heads of {0}", dept.name)
                }}</span>
                <span class="text-p-sm text-ink-gray-6">
                  {{ __("They're told who the Scoreboard champion is.") }}
                  {{
                    dept.head_roles.length
                      ? __(
                          "Anyone with the {0} role heads it too.",
                          dept.head_roles.join(", ")
                        )
                      : ""
                  }}
                </span>
                <ChipListInput
                  v-model="headsValue"
                  doctype="User"
                  :filters="{ enabled: 1, user_type: 'System User' }"
                  :placeholder="__('Add a head')"
                  mono
                />
                <div class="flex items-center gap-2">
                  <Button
                    variant="solid"
                    type="submit"
                    :label="__('Save heads')"
                    :loading="setHeads.loading"
                  />
                  <Button :label="__('Cancel')" @click="editingHeads = ''" />
                </div>
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
                  :label="__('Delete department')"
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
                  <span
                    class="truncate text-xs text-ink-gray-6"
                    :title="headsLine(dept)"
                    >{{ headsLine(dept) }}</span
                  >
                </div>

                <div class="flex shrink-0 items-center gap-0.5">
                  <Button
                    variant="ghost"
                    :tooltip="__('Move up')"
                    :label="__('Move {0} up', dept.name)"
                    :disabled="idx === 0 || move.loading"
                    @click="
                      move.submit({ department: dept.name, direction: 'up' })
                    "
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
                    :tooltip="__('Set heads')"
                    :label="__('Set heads of {0}', dept.name)"
                    @click="startHeads(dept)"
                  >
                    <template #icon
                      ><LucideUserCog class="size-4" aria-hidden="true"
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
                    :tooltip="
                      dept.is_active ? __('Deactivate') : __('Activate')
                    "
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
            </div>
          </template>
        </SettingsList>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, TextInput, toast } from "frappe-ui";
import { computed, nextTick, ref } from "vue";
import LucideArrowDown from "~icons/lucide/arrow-down";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucideBuilding2 from "~icons/lucide/building-2";
import LucideEye from "~icons/lucide/eye";
import LucideEyeOff from "~icons/lucide/eye-off";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
import LucideUserCog from "~icons/lucide/user-cog";
import ChipListInput from "../ChipListInput.vue";
import SettingsList from "../SettingsList.vue";

interface Department {
  name: string;
  department_name: string;
  sort_order: number;
  is_active: boolean;
  description?: string;
  project_count: number;
  heads: { user: string; full_name: string }[];
  /** Roles whose holders head this department as well, e.g. Digital Marketing Head. */
  head_roles: string[];
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
  toast.error(errorText(e, __("The change didn't go through. Try again.")));
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
  editingHeads.value = "";
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

// --- heads ---

function headsLine(dept: Department): string {
  const heads = [
    ...dept.heads.map((h) => h.full_name),
    ...dept.head_roles.map((role) => __("everyone with {0}", role)),
  ];
  return heads.length ? __("Heads: {0}", heads.join(", ")) : __("No heads set");
}

const editingHeads = ref("");
const headsValue = ref<string[]>([]);

function startHeads(dept: Department) {
  deleting.value = "";
  renaming.value = "";
  editingHeads.value = dept.name;
  headsValue.value = dept.heads.map((h) => h.user);
}

const setHeads = createResource({
  url: `${API}.set_department_heads`,
  onSuccess() {
    toast.success(__("Heads saved"));
    editingHeads.value = "";
    departments.reload();
  },
  onError: showError,
});

function saveHeads(dept: Department) {
  if (setHeads.loading) return;
  setHeads.submit({ department: dept.name, heads: headsValue.value });
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
