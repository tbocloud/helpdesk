<template>
  <TaskyState
    v-if="resource.error && !data"
    :icon="LucideCircleAlert"
    :title="__('Couldn\'t load the team\'s stand-up')"
    :message="
      errorText(resource.error, __('Check your connection and try again.'))
    "
    error
  >
    <Button :label="__('Retry')" @click="resource.reload()" />
  </TaskyState>

  <div v-else-if="!data" class="flex flex-col gap-4" aria-busy="true">
    <div
      v-for="i in 3"
      :key="i"
      class="h-36 animate-pulse rounded-xl border border-outline-gray-2 bg-surface-gray-1"
    />
  </div>

  <div v-else class="flex flex-col gap-4" :aria-busy="resource.loading">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <FormControl
        v-if="data.teams.length > 1"
        :model-value="data.team"
        type="select"
        class="w-full sm:w-64"
        :label="__('Team')"
        :options="data.teams.map((t) => ({ label: teamLabel(t), value: t }))"
        @update:model-value="emit('team', $event)"
      />
      <h2 v-else class="text-base-semibold text-ink-gray-9">
        {{ teamLabel(data.team) }}
      </h2>
      <p
        class="flex flex-wrap items-center gap-x-2 gap-y-1 text-p-sm text-ink-gray-7"
        aria-live="polite"
      >
        <template v-for="(part, i) in summary" :key="part.key">
          <span v-if="i" class="text-ink-gray-4" aria-hidden="true">·</span>
          <span class="inline-flex items-center gap-1.5">
            <component
              :is="part.icon"
              class="size-4 text-ink-gray-5"
              aria-hidden="true"
            />
            <span class="font-mono tabular-nums">{{ part.value }}</span>
            {{ part.label }}
          </span>
        </template>
      </p>
    </div>

    <p v-if="!data.can_lead" class="text-p-sm text-ink-gray-6">
      {{
        __(
          "Your department's stand-up: the same as the summary in its Teams channel."
        )
      }}
    </p>

    <p
      v-if="data.on_leave.length"
      class="flex items-center gap-1.5 text-p-sm text-ink-gray-6"
    >
      <LucideTreePalm
        class="size-4 shrink-0 text-ink-gray-5"
        aria-hidden="true"
      />
      {{
        __("On leave: {0}", data.on_leave.map((p) => p.full_name).join(", "))
      }}
    </p>

    <TaskyState
      v-if="!data.people.length"
      :icon="LucideMessagesSquare"
      :title="__('No stand-ups for this day')"
      :message="__('Drafts open on working days for everyone with work.')"
    />

    <template v-else>
      <SectionCard
        :title="__('Blockers and help needed')"
        :icon="LucideOctagonAlert"
        :icon-class="
          data.blockers.length || data.needs_help.length
            ? 'text-warning'
            : undefined
        "
        :count="data.blockers.length"
      >
        <p
          v-if="helpWithoutBlocker.length"
          class="flex items-center gap-1.5 border-b border-outline-gray-1 px-4 py-2.5 text-p-sm text-ink-gray-8"
        >
          <LucideLifeBuoy
            class="size-4 shrink-0 text-warning"
            aria-hidden="true"
          />
          {{ __("Asked for help: {0}", helpWithoutBlocker.join(", ")) }}
        </p>
        <ul v-if="data.blockers.length" role="list">
          <li
            v-for="blocker in data.blockers"
            :key="`${blocker.standup}:${blocker.id}`"
            class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
          >
            <p
              class="flex flex-wrap items-center gap-2 text-p-sm text-ink-gray-7"
            >
              <span class="text-base-medium text-ink-gray-9">{{
                blocker.full_name
              }}</span>
              <TaskyBadge
                v-if="blocker.needs_help"
                tone="warning"
                :icon="LucideLifeBuoy"
                :label="__('Needs help')"
              />
            </p>
            <StandupItems
              :items="[blocker]"
              :empty="''"
              class="-my-2.5"
              @open="openTask"
            />
            <div v-if="data.editable" class="flex flex-wrap gap-2">
              <AssignPicker
                :title="blocker.title"
                :label="__('Assign help')"
                :loading="helping === blockerKey(blocker)"
                touch
                @pick="(user, name) => assignHelp(blocker, user, name)"
              />
              <Button
                class="!h-11"
                :label="__('Create task')"
                @click="openDialog('task', blocker)"
              >
                <template #prefix>
                  <LucideListPlus class="size-4" aria-hidden="true" />
                </template>
              </Button>
              <Button
                v-if="blocker.reference_doctype === 'Task'"
                class="!h-11"
                :label="__('Comment')"
                @click="openDialog('comment', blocker)"
              >
                <template #prefix>
                  <LucideMessageSquare class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </div>
          </li>
        </ul>
        <p
          v-else-if="!helpWithoutBlocker.length"
          class="flex items-center gap-1.5 px-4 py-3 text-p-sm text-ink-gray-6"
        >
          <LucideCircleCheck
            class="size-4 shrink-0 text-success"
            aria-hidden="true"
          />
          {{ __("Nobody is blocked.") }}
        </p>
      </SectionCard>

      <SectionCard
        v-if="data.can_lead && pending.length && data.editable"
        :title="__('Not submitted yet')"
        :count="pending.length"
        :description="
          __('Drafts go to the channel as filled in at {0}.', data.post_at)
        "
      >
        <ul role="list">
          <li
            v-for="person in pending"
            :key="person.user"
            class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-2 last:border-b-0"
          >
            <span class="min-w-0 flex-1 truncate text-base text-ink-gray-9">
              {{ person.full_name }}
            </span>
            <Button
              class="!h-11"
              :label="__('Nudge')"
              :loading="nudging === person.name"
              :aria-label="__('Nudge {0}', person.full_name)"
              @click="nudge(person)"
            >
              <template #prefix>
                <LucideBellRing class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </li>
        </ul>
      </SectionCard>

      <SectionCard :title="__('Everyone')" :count="data.people.length">
        <ul role="list">
          <li
            v-for="person in data.people"
            :key="person.user"
            class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
          >
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-base-medium text-ink-gray-9">{{
                person.full_name
              }}</span>
              <TaskyBadge
                :tone="STATUS_TONES[person.status]"
                :icon="
                  person.status === 'Submitted' ? LucideCircleCheck : undefined
                "
                :label="statusLabel(person.status)"
              />
              <span
                v-if="person.plan_vs_done"
                class="inline-flex items-center gap-1 text-p-sm text-ink-gray-6"
                :title="
                  __(
                    'Linked work on their last stand-up\'s plan, and how much of it they finished'
                  )
                "
              >
                <LucideListChecks class="size-3.5" aria-hidden="true" />
                {{ planLine(person.plan_vs_done) }}
              </span>
              <span
                v-if="person.hours"
                class="inline-flex items-center gap-1 text-p-sm text-ink-gray-6"
              >
                <LucideClock class="size-3.5" aria-hidden="true" />
                <span class="font-mono tabular-nums">{{ person.hours }}</span>
                {{ __("h logged") }}
              </span>
              <RouterLink
                v-if="data.can_lead"
                :to="{ query: { tab: 'history', person: person.user } }"
                class="ml-auto inline-flex min-h-11 items-center rounded px-1 text-p-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              >
                {{ __("History") }}
              </RouterLink>
            </div>
            <div class="grid grid-cols-1 gap-x-6 md:grid-cols-2">
              <div
                v-for="section in (['yesterday', 'today'] as const)"
                :key="section"
                class="min-w-0"
              >
                <h3
                  class="text-xs font-medium uppercase tracking-wide text-ink-gray-5"
                >
                  {{ sectionTitle(section, data.previous_day) }}
                </h3>
                <StandupItems
                  :items="person[section]"
                  :empty="
                    section === 'today'
                      ? __('Nothing planned.')
                      : __('Nothing listed.')
                  "
                  @open="openTask"
                />
                <p
                  v-if="person.notes[section]"
                  class="pb-2 text-p-sm text-ink-gray-7"
                >
                  {{ person.notes[section] }}
                </p>
              </div>
            </div>
          </li>
        </ul>
      </SectionCard>
    </template>
  </div>

  <BlockerDialog
    v-model:blocker="dialogBlocker"
    :mode="dialogMode"
    @done="resource.reload()"
  />
  <TaskDetailDialog
    v-model:task="detailTask"
    :mine="false"
    @changed="resource.reload()"
  />
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import AssignPicker from "@/pages/home/components/AssignPicker.vue";
import TaskDetailDialog from "@/pages/tasky/components/TaskDetailDialog.vue";
import type { TaskRef } from "@/pages/tasky/components/TaskDetailDialog.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, FormControl, toast } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import LucideBellRing from "~icons/lucide/bell-ring";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideLifeBuoy from "~icons/lucide/life-buoy";
import LucideListChecks from "~icons/lucide/list-checks";
import LucideListPlus from "~icons/lucide/list-plus";
import LucideMessageSquare from "~icons/lucide/message-square";
import LucideMessagesSquare from "~icons/lucide/messages-square";
import LucideOctagonAlert from "~icons/lucide/octagon-alert";
import LucideTreePalm from "~icons/lucide/tree-palm";
import LucideUserCheck from "~icons/lucide/user-check";
import LucideUsers from "~icons/lucide/users";
import {
  sectionTitle,
  STATUS_TONES,
  statusLabel,
  teamLabel,
  type Standup,
  type StandupItem,
  type TeamBlocker,
  type TeamStandupData,
} from "../standupMeta";
import BlockerDialog from "./BlockerDialog.vue";
import StandupItems from "./StandupItems.vue";

const props = defineProps<{ team: string | null; date: string | null }>();
const emit = defineEmits<{ team: [team: string] }>();

const resource = createResource({
  url: "helpdesk.api.standup.get_team_standup",
  makeParams: () => ({
    ...(props.team ? { team: props.team } : {}),
    ...(props.date ? { date: props.date } : {}),
  }),
  auto: true,
});
watch(
  () => [props.team, props.date],
  () => resource.reload()
);

const data = computed<TeamStandupData | null>(() => resource.data ?? null);
const pending = computed(
  () => data.value?.people.filter((p) => p.status === "Draft") ?? []
);
const helpWithoutBlocker = computed(() =>
  (data.value?.people ?? [])
    .filter((p) => p.needs_help && !p.blockers.length)
    .map((p) => p.full_name)
);

const summary = computed(() => {
  const c = data.value?.counts;
  if (!c) return [];
  return [
    { key: "people", icon: LucideUsers, value: c.people, label: __("people") },
    {
      key: "submitted",
      icon: LucideUserCheck,
      value: c.submitted,
      label: __("submitted"),
    },
    {
      key: "pending",
      icon: LucideBellRing,
      value: c.pending + c.auto,
      label: __("not submitted"),
    },
    {
      key: "blockers",
      icon: LucideOctagonAlert,
      value: c.blockers,
      label: __("blockers"),
    },
  ];
});

function planLine(p: NonNullable<Standup["plan_vs_done"]>) {
  if (!p.planned) return __("{0} done, none planned", p.unplanned);
  return p.unplanned
    ? __("{0} of {1} planned done · {2} more", p.done, p.planned, p.unplanned)
    : __("{0} of {1} planned done", p.done, p.planned);
}

const detailTask = ref<TaskRef | null>(null);
function openTask(item: StandupItem) {
  detailTask.value = {
    name: item.reference_name as string,
    subject: item.title,
    project: item.project,
  };
}

const dialogBlocker = ref<TeamBlocker | null>(null);
const dialogMode = ref<"task" | "comment">("task");
function openDialog(mode: "task" | "comment", blocker: TeamBlocker) {
  dialogMode.value = mode;
  dialogBlocker.value = blocker;
}

function blockerKey(b: TeamBlocker) {
  return `${b.standup}:${b.id}`;
}

const helping = ref("");
const helpResource = createResource({
  url: "helpdesk.api.standup.assign_help",
});
async function assignHelp(blocker: TeamBlocker, user: string, name: string) {
  helping.value = blockerKey(blocker);
  try {
    await helpResource.submit({
      name: blocker.standup,
      row: blocker.id,
      helper: user,
    });
    toast.success(__("Asked {0} to help {1}", name, blocker.full_name));
    resource.reload();
  } catch (e) {
    toast.error(errorText(e, __("Couldn't ask for help. Try again.")));
  } finally {
    helping.value = "";
  }
}

const nudging = ref("");
const nudgeResource = createResource({ url: "helpdesk.api.standup.nudge" });
async function nudge(person: Standup) {
  nudging.value = person.name || "";
  try {
    await nudgeResource.submit({ name: person.name });
    toast.success(__("Nudged {0}", person.full_name));
  } catch (e) {
    toast.error(errorText(e, __("Couldn't send the nudge. Try again.")));
  } finally {
    nudging.value = "";
  }
}
</script>
