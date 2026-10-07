<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <nav
          v-if="editing"
          class="flex min-w-0 items-center gap-1.5 text-lg-medium"
          :aria-label="__('Breadcrumb')"
        >
          <button
            type="button"
            class="shrink-0 rounded text-ink-gray-5 transition-colors hover:text-ink-gray-8"
            @click="cancelEdit"
          >
            {{ __("Templates") }}
          </button>
          <LucideChevronRight
            class="size-4 shrink-0 text-ink-gray-4"
            aria-hidden="true"
          />
          <span class="truncate text-ink-gray-9" aria-current="page">{{
            editTitle
          }}</span>
        </nav>
        <div v-else class="text-lg-medium text-ink-gray-9">
          {{ __("Templates") }}
        </div>
      </template>
      <template #right-header>
        <Button
          v-if="!editing"
          variant="solid"
          :label="__('New template')"
          @click="startNew"
        >
          <template #prefix
            ><LucidePlus class="size-4" aria-hidden="true"
          /></template>
        </Button>
        <Button v-else variant="ghost" :label="__('Close')" @click="cancelEdit">
          <template #prefix
            ><LucideX class="size-4" aria-hidden="true"
          /></template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-5xl px-4 py-5 md:px-6">
        <!-- Editor -->
        <form
          v-if="editing"
          class="flex flex-col gap-5"
          novalidate
          @submit.prevent="onSave"
        >
          <section
            class="rounded-xl border border-outline-gray-2 bg-surface-base p-4 shadow-sm md:p-5"
          >
            <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <TextInput
                v-model="form.template_name"
                :label="__('Template name')"
                :placeholder="__('e.g. Manufacturing rollout')"
                required
              />
              <TextInput
                v-model="form.industry"
                :label="__('Industry')"
                :placeholder="__('e.g. Manufacturing')"
              />
              <Textarea
                v-model="form.description"
                class="sm:col-span-2"
                :label="__('Description')"
                :placeholder="__('When should a project use this template?')"
                :rows="2"
              />
            </div>
          </section>

          <section aria-labelledby="tpl-tasks">
            <div class="mb-2 flex items-center gap-2">
              <h2 id="tpl-tasks" class="text-sm font-medium text-ink-gray-7">
                {{ __("Tasks") }}
              </h2>
              <span class="font-mono text-xs tabular-nums text-ink-gray-5">{{
                form.tasks.length
              }}</span>
            </div>

            <div
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base shadow-sm"
            >
              <p
                v-if="!form.tasks.length"
                class="border-b border-outline-gray-2 px-4 py-6 text-center text-p-sm text-ink-gray-6"
              >
                {{
                  __(
                    "No tasks yet. Add the first one below — give it a phase to group related work."
                  )
                }}
              </p>

              <div
                v-for="(group, phase) in phaseGroups"
                :key="phase"
                class="border-b border-outline-gray-2"
              >
                <div class="flex items-center gap-1 bg-surface-gray-1 pr-2">
                  <button
                    type="button"
                    class="flex min-w-0 flex-1 items-center gap-2 px-4 py-2.5 text-left transition-colors hover:bg-surface-gray-2 focus-visible:bg-surface-gray-2 focus-visible:outline-none"
                    :aria-expanded="expandedPhases.has(phase)"
                    @click="togglePhase(phase)"
                  >
                    <component
                      :is="
                        expandedPhases.has(phase)
                          ? LucideChevronDown
                          : LucideChevronRight
                      "
                      class="size-4 shrink-0 text-ink-gray-5"
                      aria-hidden="true"
                    />
                    <span class="truncate text-sm font-medium text-ink-gray-8">
                      {{ phase || __("No phase") }}
                    </span>
                    <span
                      class="font-mono text-xs tabular-nums text-ink-gray-5"
                      >{{ group.length }}</span
                    >
                  </button>
                  <Button
                    variant="ghost"
                    :label="__('Remove phase {0}', phase || __('No phase'))"
                    @click="removePhaseGroup(phase)"
                  >
                    <template #icon
                      ><LucideTrash2 class="size-4 text-ink-gray-5"
                    /></template>
                  </Button>
                </div>

                <ul
                  v-if="expandedPhases.has(phase)"
                  role="list"
                  class="flex flex-col gap-2 px-4 py-3"
                >
                  <li
                    v-for="(task, idx) in group"
                    :key="task._key"
                    class="grid grid-cols-[1fr_auto] items-center gap-2 sm:grid-cols-[1fr_8rem_6rem_4.5rem_auto]"
                  >
                    <TextInput
                      v-model="task.task_name"
                      class="col-span-1"
                      :placeholder="__('Task name')"
                      :aria-label="__('Task name')"
                    />
                    <Button
                      variant="ghost"
                      class="sm:order-last"
                      :label="__('Remove task')"
                      @click="removeTaskFromGroup(phase, idx)"
                    >
                      <template #icon
                        ><LucideX class="size-4 text-ink-gray-5"
                      /></template>
                    </Button>
                    <FormControl
                      v-model="task.category"
                      type="select"
                      :options="categoryOptions()"
                      :aria-label="__('Category')"
                    />
                    <FormControl
                      v-model="task.default_priority"
                      type="select"
                      :options="priorityOptions()"
                      :aria-label="__('Priority')"
                    />
                    <TextInput
                      v-model.number="task.estimated_hours"
                      type="number"
                      min="0"
                      placeholder="0"
                      :aria-label="__('Estimated hours')"
                    />
                  </li>
                </ul>
              </div>

              <!-- Add task -->
              <div class="flex flex-col gap-2 p-3 sm:flex-row sm:items-center">
                <TextInput
                  v-model="newTaskName"
                  class="flex-1"
                  :placeholder="__('New task')"
                  :aria-label="__('New task name')"
                  @keydown.enter.prevent="addTaskToPhase"
                />
                <TextInput
                  v-model="newTaskPhase"
                  class="sm:w-40"
                  :placeholder="__('Phase')"
                  :aria-label="__('Phase for new task')"
                  list="tpl-phase-options"
                  autocomplete="off"
                  @keydown.enter.prevent="addTaskToPhase"
                />
                <datalist id="tpl-phase-options">
                  <option
                    v-for="p in Object.keys(phaseGroups).filter(Boolean)"
                    :key="p"
                    :value="p"
                  />
                </datalist>
                <Button
                  :label="__('Add task')"
                  :disabled="!newTaskName.trim()"
                  @click="addTaskToPhase"
                >
                  <template #prefix
                    ><LucidePlus class="size-4" aria-hidden="true"
                  /></template>
                </Button>
              </div>
            </div>
          </section>

          <div
            v-if="save.error"
            role="alert"
            class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
          >
            <LucideCircleAlert
              class="mt-0.5 size-4 shrink-0"
              aria-hidden="true"
            />
            {{ errorText(save.error, __("Couldn't save the template.")) }}
          </div>

          <div class="flex items-center gap-2">
            <Button
              variant="solid"
              type="submit"
              :label="editingId ? __('Update template') : __('Create template')"
              :loading="save.loading"
              :disabled="!form.template_name.trim()"
            />
            <Button variant="ghost" :label="__('Cancel')" @click="cancelEdit" />
          </div>
        </form>

        <!-- List -->
        <template v-else>
          <TaskyState
            v-if="templates.error && !templates.data"
            error
            :icon="LucideCircleAlert"
            :title="__('Couldn\'t load templates')"
            :message="__('Check your connection and try again.')"
          >
            <Button :label="__('Retry')" @click="templates.reload()" />
          </TaskyState>

          <div
            v-else-if="!templates.data"
            class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
            aria-busy="true"
          >
            <div
              v-for="i in 3"
              :key="i"
              class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4 shadow-sm"
            >
              <div class="h-4 w-1/2 animate-pulse rounded bg-surface-gray-2" />
              <div class="h-3 w-4/5 animate-pulse rounded bg-surface-gray-2" />
              <div class="h-3 w-1/4 animate-pulse rounded bg-surface-gray-2" />
            </div>
          </div>

          <div
            v-else-if="!templates.data.length"
            class="rounded-xl border border-outline-gray-2 bg-surface-base"
          >
            <TaskyState
              :icon="LucideClipboardList"
              :title="__('No templates yet')"
              :message="
                __(
                  'A template is a reusable task plan. Generate a project\'s checklist from it in one click.'
                )
              "
            >
              <Button
                variant="solid"
                :label="__('New template')"
                @click="startNew"
              >
                <template #prefix
                  ><LucidePlus class="size-4" aria-hidden="true"
                /></template>
              </Button>
            </TaskyState>
          </div>

          <ul
            v-else
            role="list"
            class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
          >
            <li v-for="t in templates.data" :key="t.name">
              <button
                type="button"
                class="group flex h-full w-full flex-col gap-2 rounded-xl border border-outline-gray-2 bg-surface-base p-4 text-left shadow-sm transition-colors hover:border-outline-gray-3 disabled:cursor-wait"
                :disabled="detail.loading"
                :aria-label="__('Edit template {0}', t.template_name)"
                @click="startEdit(t.name)"
              >
                <div class="flex w-full items-start justify-between gap-2">
                  <span class="text-base-semibold text-ink-gray-9">{{
                    t.template_name
                  }}</span>
                  <LoadingIndicator
                    v-if="detail.loading && editingId === t.name"
                    class="size-4 shrink-0 text-ink-gray-5"
                  />
                  <LucidePencil
                    v-else
                    class="size-4 shrink-0 text-ink-gray-4 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
                    aria-hidden="true"
                  />
                </div>
                <p class="line-clamp-2 text-p-sm text-ink-gray-6">
                  {{ t.description || __("No description") }}
                </p>
                <div class="mt-auto flex items-center gap-2 pt-1">
                  <span
                    class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7"
                  >
                    {{ t.industry || __("General") }}
                  </span>
                  <span class="truncate font-mono text-xs text-ink-gray-5">{{
                    t.name
                  }}</span>
                </div>
              </button>
            </li>
          </ul>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import {
  Button,
  FormControl,
  LoadingIndicator,
  TextInput,
  Textarea,
  createResource,
  toast,
} from "frappe-ui";
import { computed, reactive, ref } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideClipboardList from "~icons/lucide/clipboard-list";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
import LucideX from "~icons/lucide/x";
import TaskyState from "@/components/TaskyState.vue";
import { categoryOptions, priorityOptions } from "./taskMeta";

const editing = ref(false);
const editingId = ref("");
const newTaskName = ref("");
const newTaskPhase = ref("");
const expandedPhases = reactive<Set<string>>(new Set());

const templates = createResource({
  url: "helpdesk.tasky.api.get_templates",
  auto: true,
  transform: (d: any) => d ?? [],
  onError() {},
});

const form = reactive<{
  template_name: string;
  industry: string;
  description: string;
  tasks: any[];
}>({
  template_name: "",
  industry: "",
  description: "",
  tasks: [],
});

let _taskCounter = 0;

const phaseGroups = computed(() => {
  const groups: Record<string, any[]> = {};
  for (const t of form.tasks) {
    const p = t.phase_name || "";
    if (!groups[p]) groups[p] = [];
    groups[p].push(t);
  }
  return groups;
});

const editTitle = computed(() =>
  editingId.value ? form.template_name || editingId.value : __("New template")
);

const detail = createResource({
  url: "helpdesk.tasky.api.get_template",
  onSuccess(data: any) {
    form.template_name = data.template_name;
    form.industry = data.industry;
    form.description = data.description;
    form.tasks = data.tasks.map((t: any) => ({
      ...t,
      _key: String(++_taskCounter),
    }));
    expandedPhases.clear();
    for (const t of form.tasks) expandedPhases.add(t.phase_name || "");
    save.reset();
    editing.value = true;
  },
  onError(e: any) {
    editingId.value = "";
    toast.error(errorText(e, __("Couldn't open the template.")));
  },
});

function startEdit(name: string) {
  editingId.value = name;
  detail.submit({ template: name });
}

function startNew() {
  form.template_name = "";
  form.industry = "";
  form.description = "";
  form.tasks = [];
  expandedPhases.clear();
  save.reset();
  editing.value = true;
  editingId.value = "";
}

function cancelEdit() {
  editing.value = false;
  editingId.value = "";
  form.tasks = [];
}

function togglePhase(phase: string) {
  if (expandedPhases.has(phase)) expandedPhases.delete(phase);
  else expandedPhases.add(phase);
}

function addTaskToPhase() {
  if (!newTaskName.value.trim()) return;
  form.tasks.push({
    task_name: newTaskName.value.trim(),
    phase_name: newTaskPhase.value.trim(),
    category: "Functional",
    default_priority: "Medium",
    estimated_hours: 0,
    _key: String(++_taskCounter),
  });
  expandedPhases.add(newTaskPhase.value.trim());
  newTaskName.value = "";
  newTaskPhase.value = "";
}

function removeTaskFromGroup(phase: string, idx: number) {
  const tasks = phaseGroups.value[phase];
  if (!tasks) return;
  const task = tasks[idx];
  const globalIdx = form.tasks.indexOf(task);
  if (globalIdx !== -1) form.tasks.splice(globalIdx, 1);
}

function removePhaseGroup(phase: string) {
  form.tasks = form.tasks.filter((t: any) => (t.phase_name || "") !== phase);
  expandedPhases.delete(phase);
}

const save = createResource({
  url: "helpdesk.tasky.api.create_template",
  onSuccess() {
    toast.success(
      editingId.value ? __("Template updated") : __("Template created")
    );
    editing.value = false;
    editingId.value = "";
    form.tasks = [];
    templates.reload();
  },
  // shown inline above the save button
  onError() {},
});

function onSave() {
  if (!form.template_name.trim() || save.loading) return;
  const payload = {
    template_name: form.template_name.trim(),
    industry: form.industry,
    description: form.description,
    tasks: form.tasks.filter((t: any) => t.task_name),
  };
  if (editingId.value) {
    save.url = "helpdesk.tasky.api.update_template";
    save.submit({ template: editingId.value, ...payload });
  } else {
    save.url = "helpdesk.tasky.api.create_template";
    save.submit(payload);
  }
}
</script>
