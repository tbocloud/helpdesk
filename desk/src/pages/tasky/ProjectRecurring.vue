<template>
  <div class="flex h-full flex-col">
    <ProjectNav :project-id="projectId">
      <template #actions>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="rules.loading && !!rules.data"
          @click="rules.reload()"
        >
          <template #icon><LucideRefreshCw class="size-4" /></template>
        </Button>
      </template>
    </ProjectNav>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-5xl px-4 py-5 md:px-6">
        <TaskyState
          v-if="rules.error && !rules.data"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the recurring tasks')"
          :message="loadErrorMessage(rules.error)"
        >
          <Button :label="__('Retry')" @click="rules.reload()" />
        </TaskyState>

        <template v-else>
          <div class="mb-4 flex flex-wrap items-center gap-2">
            <div class="min-w-0 flex-1">
              <h2 class="text-lg-semibold text-ink-gray-9">
                {{ __("Recurring tasks") }}
              </h2>
              <p class="text-p-sm text-ink-gray-6">
                {{
                  __(
                    "Work that repeats, like a monthly backup check or a weekly status report. Each task is created on its own, ahead of its due date."
                  )
                }}
              </p>
            </div>
            <Button
              v-if="data?.can_manage && data.rules.length"
              :label="__('New recurring task')"
              @click="openEditor(null)"
            >
              <template #prefix>
                <LucidePlus class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>

          <!-- Loading -->
          <div
            v-if="!data"
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            aria-busy="true"
            :aria-label="__('Loading')"
          >
            <div
              v-for="i in 3"
              :key="i"
              class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-4 last:border-b-0"
            >
              <div
                class="h-3.5 w-1/3 animate-pulse rounded bg-surface-gray-2"
              />
              <div class="h-3 w-1/2 animate-pulse rounded bg-surface-gray-2" />
            </div>
          </div>

          <TaskyState
            v-else-if="!data.rules.length"
            :icon="LucideRepeat"
            :title="__('No recurring tasks yet')"
            :message="
              data.can_manage
                ? __(
                    'Set up work that repeats, such as a GST filing reminder on the 15th of every month, and its task is created and assigned automatically.'
                  )
                : __(
                    'Repeating work for this project shows up here once the project lead or manager sets it up.'
                  )
            "
          >
            <Button
              v-if="data.can_manage"
              variant="solid"
              :label="__('New recurring task')"
              @click="openEditor(null)"
            >
              <template #prefix>
                <LucidePlus class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </TaskyState>

          <ul
            v-else
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            role="list"
            :aria-label="__('Recurring tasks')"
          >
            <li
              v-for="rule in data.rules"
              :key="rule.name"
              class="flex flex-col gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0 md:flex-row md:items-start md:gap-4"
            >
              <div class="flex min-w-0 flex-1 flex-col gap-1">
                <div class="flex min-w-0 flex-wrap items-center gap-2">
                  <span
                    class="min-w-0 truncate text-base-medium"
                    :class="
                      rule.is_active ? 'text-ink-gray-9' : 'text-ink-gray-6'
                    "
                    :title="rule.subject"
                    >{{ rule.subject }}</span
                  >
                  <TaskyBadge
                    v-if="rule.state !== 'active'"
                    :label="__(recurringStateMeta(rule.state).label)"
                    :tone="recurringStateMeta(rule.state).tone"
                    :icon="recurringStateMeta(rule.state).icon"
                  />
                  <TaskyBadge
                    v-if="rule.is_key"
                    :label="__('Key')"
                    :icon="LucideKeyRound"
                  />
                </div>
                <p class="flex items-center gap-1.5 text-p-sm text-ink-gray-7">
                  <LucideRepeat
                    class="size-3.5 shrink-0 text-ink-gray-5"
                    aria-hidden="true"
                  />
                  <span>{{ rule.schedule }}</span>
                </p>
                <div
                  class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-gray-6"
                >
                  <span>{{
                    rule.assignee_name
                      ? __("For {0}", rule.assignee_name)
                      : __("Unassigned")
                  }}</span>
                  <template v-if="rule.is_active && rule.next_due_date">
                    <span aria-hidden="true">·</span>
                    <span class="tabular-nums">
                      {{
                        __(
                          "Next due {0}",
                          dateFormat(rule.next_due_date, "ddd, D MMM YYYY")
                        )
                      }}
                      <template
                        v-if="
                          rule.next_create_on &&
                          rule.next_create_on !== rule.next_due_date
                        "
                      >
                        {{
                          __(
                            "(created {0})",
                            dateFormat(rule.next_create_on, "D MMM")
                          )
                        }}
                      </template>
                    </span>
                  </template>
                  <template v-if="rule.occurrences_created">
                    <span aria-hidden="true">·</span>
                    <span class="tabular-nums">{{
                      rule.occurrences_created === 1
                        ? __("1 task created")
                        : __(
                            "{0} tasks created",
                            String(rule.occurrences_created)
                          )
                    }}</span>
                  </template>
                </div>
                <p
                  v-if="!rule.is_active && rule.inactive_reason"
                  class="text-xs text-ink-gray-6"
                >
                  {{ rule.inactive_reason }}
                </p>
                <button
                  v-if="rule.last_task"
                  type="button"
                  class="mt-1 inline-flex min-w-0 max-w-full items-center gap-1.5 self-start rounded text-left text-xs text-ink-gray-7 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                  @click="
                    openTask = {
                      name: rule.last_task.name,
                      subject: rule.last_task.subject,
                      project: projectId,
                    }
                  "
                >
                  <component
                    :is="taskStatusMeta(rule.last_task.status).icon"
                    class="size-3.5 shrink-0 text-ink-gray-5"
                    aria-hidden="true"
                  />
                  <span class="shrink-0">{{ __("Last created:") }}</span>
                  <span class="truncate underline">{{
                    rule.last_task.subject
                  }}</span>
                  <span
                    v-if="rule.last_task.due_date"
                    class="shrink-0 tabular-nums text-ink-gray-5"
                    >{{
                      __(
                        "due {0}",
                        dateFormat(rule.last_task.due_date, "D MMM")
                      )
                    }}</span
                  >
                </button>
              </div>

              <div
                v-if="data.can_manage"
                class="flex shrink-0 items-center gap-1 md:justify-end"
              >
                <Button
                  v-if="rule.state !== 'stopped'"
                  :label="rule.is_active ? __('Pause') : __('Resume')"
                  :loading="busy === rule.name"
                  @click="setActive(rule, !rule.is_active)"
                >
                  <template #prefix>
                    <component
                      :is="rule.is_active ? LucidePause : LucidePlay"
                      class="size-4"
                      aria-hidden="true"
                    />
                  </template>
                </Button>
                <Dropdown :options="menu(rule)">
                  <Button
                    variant="ghost"
                    :aria-label="__('More actions for {0}', rule.subject)"
                  >
                    <template #icon>
                      <LucideEllipsis class="size-4" aria-hidden="true" />
                    </template>
                  </Button>
                </Dropdown>
              </div>
            </li>
          </ul>
        </template>
      </div>
    </div>

    <RecurringTaskDialog
      v-if="data?.can_manage"
      v-model:open="showEditor"
      :project-id="projectId"
      :rule="editing"
      @saved="rules.reload()"
    />

    <TaskDetailDialog v-model:task="openTask" @changed="rules.reload()" />

    <Dialog
      :open="!!deleting"
      :title="__('Delete this recurring task?')"
      size="md"
      @update:open="(v: boolean) => !v && (deleting = null)"
    >
      <template #default>
        <p class="text-p-base text-ink-gray-8">
          {{
            deleting?.occurrences_created
              ? __(
                  "No new tasks will be created. The {0} tasks it already created stay in the project.",
                  String(deleting.occurrences_created)
                )
              : __("No tasks will be created from it. This can't be undone.")
          }}
        </p>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="deleting = null" />
          <Button
            variant="solid"
            theme="red"
            :label="__('Delete recurring task')"
            :loading="!!deleting && busy === deleting.name"
            @click="remove()"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { dateFormat, errorText } from "@/utils";
import {
  Button,
  Dialog,
  Dropdown,
  call,
  createResource,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideKeyRound from "~icons/lucide/key-round";
import LucidePause from "~icons/lucide/pause";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlay from "~icons/lucide/play";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideRepeat from "~icons/lucide/repeat";
import LucideTrash2 from "~icons/lucide/trash-2";
import ProjectNav from "./components/ProjectNav.vue";
import RecurringTaskDialog from "./components/RecurringTaskDialog.vue";
import TaskDetailDialog, {
  type TaskRef,
} from "./components/TaskDetailDialog.vue";
import { recurringStateMeta, type RecurringRule } from "./recurringMeta";
import { loadErrorMessage, taskStatusMeta } from "./taskMeta";

interface RecurringList {
  rules: RecurringRule[];
  can_manage: boolean;
}

const props = defineProps<{ projectId: string }>();

const rules = createResource({
  url: "helpdesk.api.recurring_tasks.get_recurring_tasks",
  makeParams: () => ({ project: props.projectId }),
  auto: true,
  onError() {},
});

watch(
  () => props.projectId,
  () => rules.reload()
);

const data = computed(() => rules.data as RecurringList | undefined);

const showEditor = ref(false);
const editing = ref<RecurringRule | null>(null);
const openTask = ref<TaskRef | null>(null);
const deleting = ref<RecurringRule | null>(null);
const busy = ref<string | null>(null);

function openEditor(rule: RecurringRule | null) {
  editing.value = rule;
  showEditor.value = true;
}

function menu(rule: RecurringRule) {
  return [
    {
      label: __("Edit"),
      icon: LucidePencil,
      onClick: () => openEditor(rule),
    },
    {
      label: __("Delete"),
      icon: LucideTrash2,
      onClick: () => (deleting.value = rule),
    },
  ];
}

async function setActive(rule: RecurringRule, active: boolean) {
  busy.value = rule.name;
  try {
    await call("helpdesk.api.recurring_tasks.set_recurring_task_active", {
      name: rule.name,
      active,
    });
    toast.success(
      active ? __("{0} resumed", rule.subject) : __("{0} paused", rule.subject)
    );
    await rules.reload();
  } catch (e) {
    toast.error(
      errorText(
        e,
        active
          ? __("Couldn't resume the recurring task.")
          : __("Couldn't pause the recurring task.")
      )
    );
  } finally {
    busy.value = null;
  }
}

async function remove() {
  const rule = deleting.value;
  if (!rule || busy.value) return;
  busy.value = rule.name;
  try {
    await call("helpdesk.api.recurring_tasks.delete_recurring_task", {
      name: rule.name,
    });
    toast.success(__("Recurring task deleted"));
    deleting.value = null;
    await rules.reload();
  } catch (e) {
    toast.error(errorText(e, __("Couldn't delete the recurring task.")));
  } finally {
    busy.value = null;
  }
}
</script>
