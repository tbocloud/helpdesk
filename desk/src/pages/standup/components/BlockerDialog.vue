<template>
  <!-- the project and people pickers open outside the dialog, so an outside
       click must not close it; Cancel and the close button still do -->
  <Dialog
    :open="!!blocker"
    :title="
      mode === 'task'
        ? __('Create a task from this blocker')
        : __('Comment on the blocking task')
    "
    size="md"
    :dismissible="false"
    @update:open="(value: boolean) => !value && close()"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <p v-if="blocker" class="text-p-sm text-ink-gray-6">
        {{ __("{0}: {1}", blocker.full_name, blocker.title) }}
        <template v-if="blocker.detail"> · {{ blocker.detail }}</template>
      </p>
      <template v-if="mode === 'task'">
        <FormControl
          v-model="subject"
          :label="__('Task')"
          maxlength="140"
          :placeholder="__('What unblocks them')"
        />
        <Link
          v-model="project"
          doctype="Project"
          :filters="{ status: 'Open' }"
          :label="__('Project')"
          :placeholder="__('Select project')"
        />
        <Combobox
          v-model="assignee"
          :options="peopleOptions"
          :label="__('Assign to')"
          :placeholder="__('Nobody yet')"
        />
        <FormControl v-model="dueDate" type="date" :label="__('Due date')" />
      </template>
      <FormControl
        v-else
        v-model="comment"
        type="textarea"
        :rows="4"
        maxlength="2000"
        :label="__('Comment')"
        :placeholder="
          __('e.g. Reshma, can you send Anu the VPN details today?')
        "
      />
      <div
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ errorMessage }}</span>
      </div>
    </form>

    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="mode === 'task' ? __('Create task') : __('Add comment')"
          :loading="action.loading"
          :disabled="!ready || action.loading"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import {
  useAssignablePeople,
  type AssignablePerson,
} from "@/composables/assignablePeople";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  Combobox,
  createResource,
  Dialog,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import type { TeamBlocker } from "../standupMeta";

const props = defineProps<{ mode: "task" | "comment" }>();
const blocker = defineModel<TeamBlocker | null>("blocker", { default: null });
const emit = defineEmits<{ done: [] }>();

const formId = `blocker-${useId()}`;
const subject = ref("");
const project = ref("");
const assignee = ref<string | null>(null);
const dueDate = ref("");
const comment = ref("");
const errorMessage = ref("");

const { people } = useAssignablePeople();
const peopleOptions = computed(() =>
  ((people.data ?? []) as AssignablePerson[]).map((p) => ({
    label: p.full_name || p.name,
    value: p.name,
  }))
);

watch(blocker, (b) => {
  errorMessage.value = "";
  subject.value = b ? b.title : "";
  project.value = b?.project || "";
  assignee.value = null;
  dueDate.value = "";
  comment.value = "";
});

const ready = computed(() =>
  props.mode === "task"
    ? !!subject.value.trim() && !!project.value
    : !!comment.value.trim()
);

const action = createResource({
  url: "helpdesk.api.standup.create_task_from_blocker",
  // shown in the dialog instead of the global error toast
  onError() {},
});
const commentAction = createResource({
  url: "helpdesk.tasky.api.add_task_comment",
  onError() {},
});

function close() {
  blocker.value = null;
}

async function submit() {
  const b = blocker.value;
  if (!b || !ready.value) return;
  errorMessage.value = "";
  try {
    if (props.mode === "task") {
      const result = await action.submit({
        name: b.standup,
        row: b.id,
        project: project.value,
        subject: subject.value.trim(),
        assigned_to: assignee.value || undefined,
        due_date: dueDate.value || undefined,
      });
      toast.success(__("Task {0} created", result.task));
    } else {
      await commentAction.submit({
        task: b.reference_name,
        content: comment.value.trim(),
      });
      toast.success(__("Comment added to {0}", b.reference_name as string));
    }
    emit("done");
    close();
  } catch (e) {
    errorMessage.value = errorText(
      e,
      __("That didn't work. Check the details and try again.")
    );
  }
}
</script>
