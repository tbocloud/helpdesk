<template>
  <Dialog
    :open="!!task"
    :title="__('Move to another project')"
    :message="task?.subject"
    size="md"
    @update:open="onOpenChange"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <div
        v-if="projects.error && !projects.data"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span class="flex-1">{{
          errorText(projects.error, __("Couldn't load your projects."))
        }}</span>
        <Button size="sm" :label="__('Retry')" @click="projects.reload()" />
      </div>

      <template v-else>
        <!-- Combobox layers inside the dialog, so Escape and clicking outside still close it -->
        <Combobox
          v-model="target"
          :label="__('Move to')"
          :options="options"
          :placeholder="__('Pick a project')"
          :loading="projects.loading"
          :empty-text="__('No matching project')"
          required
        />
        <p
          v-if="projects.data && !options.length"
          class="text-p-sm text-ink-gray-6"
        >
          {{
            __(
              "There's no other open project you can add tasks to. Ask a project manager to add you to the right one."
            )
          }}
        </p>
      </template>

      <ul class="flex flex-col gap-1.5 text-p-sm text-ink-gray-6">
        <li v-if="task?.phase" class="flex items-start gap-2">
          <LucideLayers
            class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          {{
            __(
              "Its phase, {0}, stays only if the new project has a phase with that name.",
              task.phase
            )
          }}
        </li>
        <li class="flex items-start gap-2">
          <LucideLink2Off
            class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          {{
            task?.depends_on_task
              ? __(
                  "It stops waiting on {0}, and tasks here that wait on it stop waiting: tasks only wait on tasks in their own project.",
                  task.depends_on_subject || task.depends_on_task
                )
              : __(
                  "Tasks here that wait on it stop waiting: tasks only wait on tasks in their own project."
                )
          }}
        </li>
        <li v-if="task?.assigned_to" class="flex items-start gap-2">
          <LucideUser
            class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          {{
            __(
              "{0} keeps the task and is told it moved.",
              task.assigned_to_name || task.assigned_to
            )
          }}
        </li>
      </ul>

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
          :label="__('Move task')"
          :loading="move.loading"
          :disabled="!target"
        >
          <template #prefix>
            <LucideFolderInput class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, Combobox, Dialog, createResource, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFolderInput from "~icons/lucide/folder-input";
import LucideLayers from "~icons/lucide/layers";
import LucideLink2Off from "~icons/lucide/link-2-off";
import LucideUser from "~icons/lucide/user";

interface MovableTask {
  name: string;
  subject?: string;
  project?: string | null;
  phase?: string;
  depends_on_task?: string | null;
  depends_on_subject?: string | null;
  assigned_to?: string | null;
  assigned_to_name?: string | null;
}

interface ProjectOption {
  name: string;
  project_name?: string;
  customer?: string | null;
  status?: string;
  can_add_tasks?: boolean;
}

const props = defineProps<{
  /** The task to move; the dialog is open while this is set. */
  task: MovableTask | null;
}>();

const emit = defineEmits<{
  "update:task": [value: null];
  moved: [task: Record<string, any>];
}>();

const formId = `tasky-move-task-${useId()}`;
const target = ref<string | null>(null);

const projects = createResource({
  url: "helpdesk.tasky.api.get_projects",
  // shown inline in the dialog
  onError() {},
});

// the server takes only open projects the mover can add tasks to
const options = computed(() =>
  ((projects.data ?? []) as ProjectOption[])
    .filter(
      (p) =>
        p.can_add_tasks &&
        (p.status || "Open") === "Open" &&
        p.name !== props.task?.project
    )
    .map((p) => ({
      label: p.project_name || p.name,
      value: p.name,
      description: p.customer || p.name,
    }))
);

const move = createResource({
  url: "helpdesk.tasky.api.move_task_to_project",
  onSuccess(data: Record<string, any>) {
    const name = options.value.find((o) => o.value === target.value)?.label;
    toast.success(__("Task moved to {0}", name || data.project));
    if (data.not_on_team?.length)
      toast.warning(
        __(
          "{0} isn't on that project's team yet. Ask its manager or lead to add them.",
          props.task?.assigned_to_name || data.not_on_team.join(", ")
        )
      );
    emit("moved", data);
    emit("update:task", null);
  },
  // shown inline in the dialog instead of the global error toast
  onError() {},
});

const errorMessage = computed(() =>
  move.error ? errorText(move.error, __("Couldn't move the task.")) : ""
);

watch(
  () => props.task?.name,
  (name) => {
    if (!name) return;
    target.value = null;
    move.reset();
    if (!projects.data && !projects.loading) projects.reload();
  },
  { immediate: true }
);

function onOpenChange(open: boolean) {
  if (!open) emit("update:task", null);
}

function submit() {
  if (!props.task || !target.value || move.loading) return;
  move.submit({ task: props.task.name, project: target.value });
}
</script>
