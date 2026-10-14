<template>
  <TaskyState
    v-if="resource.error && !data"
    :icon="LucideCircleAlert"
    :title="__('Couldn\'t load your stand-up')"
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

  <TaskyState
    v-else-if="!data.enabled && !form"
    :icon="LucideMessagesSquare"
    :title="__('The daily stand-up isn\'t switched on')"
    :message="
      __(
        'An admin turns it on in Settings → Stand-up. Until then there is nothing to fill in.'
      )
    "
  />

  <TaskyState
    v-else-if="!form"
    :icon="LucideCalendarOff"
    :title="
      data.editable ? __('No stand-up today') : __('No stand-up that day')
    "
    :message="
      data.is_working_day
        ? __('There was nothing to report: no open work and nothing done.')
        : __('It wasn\'t a working day.')
    "
  />

  <form v-else class="flex flex-col gap-4" @submit.prevent="save(true)">
    <p
      class="flex flex-wrap items-center gap-x-2 gap-y-1 text-p-sm text-ink-gray-6"
      aria-live="polite"
    >
      <TaskyBadge
        :tone="STATUS_TONES[form.status]"
        :icon="form.status === 'Submitted' ? LucideCircleCheck : undefined"
        :label="statusLabel(form.status)"
      />
      <span v-if="form.status === 'Submitted' && form.submitted_on">
        {{ __("at {0}", dayjs(form.submitted_on).format("HH:mm")) }}
      </span>
      <span v-if="data.editable && !data.posted">
        {{ __("Goes to your team at {0}.", data.post_at) }}
      </span>
      <span v-else-if="data.editable">
        {{ __("Your team's summary went out at {0}.", data.post_at) }}
      </span>
    </p>

    <SectionCard
      v-for="section in SECTIONS"
      :key="section"
      :title="sectionTitle(section, data.previous_day)"
      :icon="section === 'blockers' ? LucideOctagonAlert : undefined"
      :icon-class="
        section === 'blockers' && form.blockers.length
          ? 'text-warning'
          : undefined
      "
      :count="form[section].length"
      :description="describe(section)"
    >
      <div class="px-4">
        <StandupItems
          :items="form[section]"
          :removable="data.editable"
          :empty="emptyText(section)"
          @remove="remove(section, $event)"
          @open="openTask"
        />
        <p
          v-if="
            section === 'yesterday' && form.hours !== null && form.hours > 0
          "
          class="flex items-center gap-1.5 border-t border-outline-gray-1 py-2.5 text-p-sm text-ink-gray-6"
        >
          <LucideClock
            class="size-4 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          <span>
            <span class="font-mono tabular-nums">{{ form.hours }}</span>
            {{ __("hours logged") }}
          </span>
        </p>
      </div>

      <div
        v-if="data.editable"
        class="border-t border-outline-gray-1 px-4 py-3"
      >
        <div v-if="section === 'blockers'" class="flex items-end gap-2">
          <FormControl
            v-model="newBlocker"
            class="min-w-0 flex-1"
            :label="__('Add a blocker')"
            :placeholder="__('e.g. Waiting for VPN access from the client')"
            maxlength="300"
            @keydown.enter.prevent="addBlocker"
          />
          <Button
            class="!h-11"
            :label="__('Add')"
            :disabled="!newBlocker.trim()"
            @click="addBlocker"
          >
            <template #prefix>
              <LucidePlus class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
        <FormControl
          v-else
          v-model="form.notes[section as NoteSection]"
          type="textarea"
          :rows="2"
          maxlength="1000"
          :label="
            section === 'today'
              ? __('Anything else today')
              : __('Anything else you did')
          "
          :placeholder="
            section === 'today'
              ? __('e.g. Call Malabar Traders about the GST file')
              : __('e.g. Helped Reshma with the payroll export')
          "
        />
      </div>
      <p
        v-else-if="form.notes[section as NoteSection]"
        class="border-t border-outline-gray-1 px-4 py-2.5 text-p-sm text-ink-gray-7"
      >
        {{ form.notes[section as NoteSection] }}
      </p>
    </SectionCard>

    <div
      v-if="data.editable"
      class="sticky bottom-0 z-10 -mx-4 flex items-center gap-3 border-t border-outline-gray-2 bg-surface-base px-4 py-3 sm:static sm:mx-0 sm:rounded-xl sm:border"
    >
      <div class="flex min-h-11 items-center">
        <Checkbox v-model="form.needs_help" :label="__('I need help')" />
      </div>
      <span class="flex-1" />
      <Button
        v-if="form.status !== 'Submitted'"
        class="!h-11"
        :label="__('Save draft')"
        :loading="saving === 'save'"
        :disabled="!!saving || !dirty"
        @click="save(false)"
      />
      <Button
        variant="solid"
        type="submit"
        class="!h-11"
        :label="
          form.status === 'Submitted'
            ? __('Update stand-up')
            : __('Submit stand-up')
        "
        :loading="saving === 'submit'"
        :disabled="!!saving || (form.status === 'Submitted' && !dirty)"
      />
    </div>
  </form>

  <TaskDetailDialog
    v-model:task="detailTask"
    :mine="true"
    @changed="resource.reload()"
  />
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import TaskDetailDialog from "@/pages/tasky/components/TaskDetailDialog.vue";
import type { TaskRef } from "@/pages/tasky/components/TaskDetailDialog.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  Checkbox,
  createResource,
  dayjs,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCalendarOff from "~icons/lucide/calendar-off";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideMessagesSquare from "~icons/lucide/messages-square";
import LucideOctagonAlert from "~icons/lucide/octagon-alert";
import LucidePlus from "~icons/lucide/plus";
import {
  SECTIONS,
  sectionTitle,
  STATUS_TONES,
  statusLabel,
  type MyStandupData,
  type NoteSection,
  type Section,
  type Standup,
  type StandupItem,
} from "../standupMeta";
import StandupItems from "./StandupItems.vue";

const props = defineProps<{ date: string | null }>();

const resource = createResource({
  url: "helpdesk.api.standup.get_my_standup",
  makeParams: () => (props.date ? { date: props.date } : {}),
  auto: true,
});
watch(
  () => props.date,
  () => resource.reload()
);

const data = computed<MyStandupData | null>(() => resource.data ?? null);
const form = ref<Standup | null>(null);
const saved = ref("");
const dirty = computed(() => !!form.value && snapshot() !== saved.value);

function load(standup: Standup | null | undefined) {
  form.value = standup ? JSON.parse(JSON.stringify(standup)) : null;
  saved.value = snapshot();
}
watch(
  () => data.value?.standup,
  (standup, before) => {
    // a reload (e.g. after changing a task from a row) must not throw away
    // unsaved edits to the same stand-up
    const same =
      !!standup &&
      !!before &&
      standup.date === before.date &&
      standup.name === before.name;
    if (same && dirty.value) return;
    load(standup);
  },
  { immediate: true }
);

function snapshot() {
  if (!form.value) return "";
  const { yesterday, today, blockers, notes, needs_help } = form.value;
  return JSON.stringify({ yesterday, today, blockers, notes, needs_help });
}

function describe(section: Section) {
  if (section === "yesterday")
    return __("Filled in from what you finished and replied to.");
  if (section === "today")
    return __("Due today, in progress and due next, plus your plan for today.");
  return __("Held work, work waiting on someone, and late key tasks.");
}

function emptyText(section: Section) {
  return {
    yesterday: __("Nothing finished that day."),
    today: __("Nothing due or in progress."),
    blockers: __("Nothing is blocking you."),
  }[section];
}

function remove(section: Section, index: number) {
  form.value?.[section].splice(index, 1);
}

const newBlocker = ref("");
function addBlocker() {
  const title = newBlocker.value.trim();
  if (!title || !form.value) return;
  form.value.blockers.push({
    id: null,
    kind: "note",
    title,
    detail: null,
    reference_doctype: null,
    reference_name: null,
    project: null,
    auto: false,
    route: null,
    helper: null,
    helper_name: null,
    help_task: null,
  });
  newBlocker.value = "";
}

const detailTask = ref<TaskRef | null>(null);
function openTask(item: StandupItem) {
  detailTask.value = {
    name: item.reference_name as string,
    subject: item.title,
    project: item.project,
  };
}

const saving = ref<"" | "save" | "submit">("");
const saveResource = createResource({
  url: "helpdesk.api.standup.save_standup",
});
const submitResource = createResource({
  url: "helpdesk.api.standup.submit_standup",
});

async function save(submit: boolean) {
  if (!form.value || saving.value) return;
  saving.value = submit ? "submit" : "save";
  const { yesterday, today, blockers, notes, needs_help } = form.value;
  try {
    const result = await (submit ? submitResource : saveResource).submit({
      values: {
        yesterday,
        today,
        blockers,
        notes,
        needs_help: needs_help ? 1 : 0,
      },
    });
    // what was saved is the new starting point, edits and all
    load(result.standup);
    resource.setData(result);
    toast.success(submit ? __("Stand-up submitted") : __("Draft saved"));
  } catch (e) {
    toast.error(errorText(e, __("Couldn't save your stand-up. Try again.")));
  } finally {
    saving.value = "";
  }
}
</script>
