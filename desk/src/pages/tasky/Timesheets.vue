<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Timesheets") }}</div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :aria-label="__('Refresh')"
          :loading="(timesheets.loading && !!timesheets.data) || days.loading"
          @click="reload"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          :label="__('Download CSV')"
          :tooltip="__('One row per time log, with the filters below')"
          @click="downloadCsv"
        >
          <template #prefix>
            <LucideDownload class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button variant="solid" :label="__('Log time')" @click="openForm">
          <template #prefix>
            <LucidePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <p class="text-p-sm text-ink-gray-6">
          {{
            scope === "team"
              ? __(
                  "Hours your team logged on the projects you lead or manage, as a record of the work. Pick dates to see a period."
                )
              : __(
                  "Hours you logged against projects and tasks, as a record of your work. Pick dates to see a period."
                )
          }}
        </p>

        <TaskyState
          v-if="timesheets.error && !timesheets.data"
          class="mt-6"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the timesheets')"
          :message="
            errorText(
              timesheets.error,
              __('Check your connection and try again.')
            )
          "
        >
          <Button :label="__('Retry')" @click="reload" />
        </TaskyState>

        <template v-else>
          <!-- Whose and when -->
          <div
            class="mt-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between"
          >
            <TabButtons
              v-if="canSeeTeam"
              v-model="scope"
              class="self-start lg:self-auto"
              size="md"
              :aria-label="__('Whose timesheets')"
              :options="SCOPES.map((o) => ({ label: o.label, value: o.key }))"
            />

            <div
              class="flex flex-wrap items-end gap-3"
              role="group"
              :aria-label="__('Filter timesheets')"
            >
              <div v-if="scope === 'team'" class="w-full sm:w-56">
                <FormControl
                  v-model="filters.agent"
                  type="select"
                  :label="__('Agent')"
                  :options="agentOptions"
                />
              </div>
              <div class="w-full sm:w-56">
                <FormControl
                  v-model="filters.project"
                  type="select"
                  :label="__('Project')"
                  :options="projectFilterOptions"
                />
              </div>
              <div class="w-[calc(50%-0.375rem)] sm:w-40">
                <FormControl
                  v-model="filters.from_date"
                  type="date"
                  :label="__('From')"
                />
              </div>
              <div class="w-[calc(50%-0.375rem)] sm:w-40">
                <FormControl
                  v-model="filters.to_date"
                  type="date"
                  :label="__('To')"
                />
              </div>
              <Button
                v-if="hasFilters"
                variant="ghost"
                :label="__('Clear filters')"
                @click="clearFilters"
              >
                <template #prefix>
                  <LucideX class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </div>
          </div>

          <!-- Summary of the period -->
          <div class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <StatTile
              :label="__('Hours logged')"
              :value="summary.data ? formatHours(summary.data.hours) : '—'"
              :sub="periodLabel"
              :icon="LucideTimer"
              icon-tone="info"
              :loading="summaryLoading"
            />
            <StatTile
              :label="__('Timesheets')"
              :value="sheetCount"
              :icon="LucideFileClock"
              :loading="listLoading"
            />
            <StatTile
              :label="__('Drafts')"
              :value="draftCount"
              :sub="drafts ? __('Not submitted yet') : undefined"
              :icon="LucideCircleDashed"
              :loading="listLoading"
            />
          </div>

          <div
            class="mt-4 grid grid-cols-1 gap-4"
            :class="scope === 'team' ? 'lg:grid-cols-2' : ''"
          >
            <SectionCard
              v-for="breakdown in breakdowns"
              :key="breakdown.key"
              :title="breakdown.title"
              :description="breakdown.description"
            >
              <div
                v-if="summaryLoading"
                class="flex flex-col gap-3 p-4"
                :aria-label="__('Loading')"
              >
                <div
                  v-for="i in 3"
                  :key="i"
                  class="h-4 animate-pulse rounded bg-surface-gray-2"
                />
              </div>
              <div
                v-else-if="summary.error"
                class="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-p-sm text-ink-gray-6"
                role="alert"
              >
                {{ errorText(summary.error, __("Couldn't add up the hours.")) }}
                <Button
                  size="sm"
                  :label="__('Retry')"
                  @click="summary.reload()"
                />
              </div>
              <p
                v-else-if="!breakdown.rows.length"
                class="px-4 py-3 text-p-sm text-ink-gray-5"
              >
                {{ __("No time logged in these dates.") }}
              </p>
              <ul v-else role="list">
                <li
                  v-for="row in breakdown.rows.slice(0, BREAKDOWN_ROWS)"
                  :key="row.key"
                  class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 border-b border-outline-gray-1 px-4 py-2.5 last:border-b-0"
                >
                  <span class="truncate text-sm text-ink-gray-8">
                    {{ row.label }}
                  </span>
                  <span
                    class="text-right font-mono text-sm tabular-nums text-ink-gray-8"
                  >
                    {{ formatHours(row.hours) }}
                  </span>
                  <span
                    class="col-span-2 block h-1 overflow-hidden rounded-full bg-surface-gray-2"
                    aria-hidden="true"
                  >
                    <span
                      class="block h-full rounded-full bg-surface-gray-6"
                      :style="{ width: `${share(row.hours)}%` }"
                    />
                  </span>
                </li>
                <li
                  v-if="breakdown.rows.length > BREAKDOWN_ROWS"
                  class="px-4 py-2.5 text-p-sm tabular-nums text-ink-gray-5"
                >
                  {{ moreLabel(breakdown.rows) }}
                </li>
              </ul>
            </SectionCard>
          </div>

          <!-- The timesheets, as a list or day by day -->
          <div
            class="mt-6 flex flex-wrap items-center justify-between gap-x-4 gap-y-2"
          >
            <TabButtons
              v-model="view"
              size="md"
              :aria-label="__('Show the timesheets')"
              :options="VIEWS.map((o) => ({ label: o.label, value: o.key }))"
            />
            <p v-if="view === 'day'" class="text-p-sm text-ink-gray-6">
              {{
                __("Each day's hours by task or project, with the work notes.")
              }}
            </p>
          </div>

          <div
            v-if="view === 'day'"
            class="mt-3 flex flex-col gap-4"
            :aria-busy="dayLoading"
          >
            <TaskyState
              v-if="rangeError"
              class="rounded-xl border border-outline-gray-2 bg-surface-base"
              :icon="LucideCalendarRange"
              :title="__('Pick a shorter period')"
              :message="rangeError"
            />
            <SectionCard
              v-else-if="dayLoading"
              :title="__('Loading the days')"
              class="overflow-hidden"
            >
              <div class="flex flex-col gap-3 p-4" :aria-label="__('Loading')">
                <div
                  v-for="i in 4"
                  :key="i"
                  class="h-4 animate-pulse rounded bg-surface-gray-2"
                />
              </div>
            </SectionCard>
            <TaskyState
              v-else-if="days.error"
              class="rounded-xl border border-outline-gray-2 bg-surface-base"
              error
              :icon="LucideCircleAlert"
              :title="__('Couldn\'t load the days')"
              :message="
                errorText(
                  days.error,
                  __('Check your connection and try again.')
                )
              "
            >
              <Button :label="__('Retry')" @click="days.reload()" />
            </TaskyState>
            <TaskyState
              v-else-if="dayData?.too_many"
              class="rounded-xl border border-outline-gray-2 bg-surface-base"
              :icon="LucideCalendarRange"
              :title="__('Too many time logs to show day by day')"
              :message="
                __(
                  'Pick fewer days or one person, or download the CSV for all of them.'
                )
              "
            >
              <Button :label="__('Download CSV')" @click="downloadCsv">
                <template #prefix>
                  <LucideDownload class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </TaskyState>
            <TaskyState
              v-else-if="!dayPeople.length"
              class="rounded-xl border border-outline-gray-2 bg-surface-base"
              :icon="LucideSearchX"
              :title="__('No time logged in these dates')"
              :message="
                hasFilters
                  ? __('Try other dates, or clear the filters.')
                  : __('Pick other dates, or log time for this week.')
              "
            >
              <Button
                v-if="hasFilters"
                :label="__('Clear filters')"
                @click="clearFilters"
              />
              <Button
                v-else
                variant="solid"
                :label="__('Log time')"
                @click="openForm"
              >
                <template #prefix>
                  <LucidePlus class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </TaskyState>

            <SectionCard
              v-for="person in dayPeople"
              v-else
              :key="person.user"
              :title="person.full_name"
              :description="personLine(person)"
              class="overflow-hidden"
            >
              <section
                v-for="day in person.days"
                :key="day.date"
                :aria-label="dayLabel(person, day)"
                class="border-b border-outline-gray-2 last:border-b-0"
              >
                <h3
                  class="flex items-baseline justify-between gap-4 bg-surface-gray-1 px-4 py-2 text-sm-medium text-ink-gray-8"
                >
                  <span class="tabular-nums">{{ formatDay(day.date) }}</span>
                  <span class="font-mono tabular-nums">
                    <span class="sr-only">{{ __("Total") }}</span>
                    {{ formatHours(day.hours) }}
                  </span>
                </h3>
                <ul role="list">
                  <li
                    v-for="entry in day.entries"
                    :key="`${entry.project}-${entry.task}`"
                    class="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 border-t border-outline-gray-1 px-4 py-2.5"
                  >
                    <div class="min-w-0">
                      <div class="break-words text-sm text-ink-gray-9">
                        {{ entryTitle(entry) }}
                      </div>
                      <div
                        v-if="entry.task && entry.project"
                        class="mt-0.5 truncate text-xs text-ink-gray-5"
                        :title="entry.project_name || entry.project"
                      >
                        {{ entry.project_name || entry.project }}
                      </div>
                      <p
                        v-for="(note, i) in entry.notes"
                        :key="i"
                        class="mt-1 whitespace-pre-line break-words text-p-sm text-ink-gray-7"
                      >
                        {{ note }}
                      </p>
                    </div>
                    <span
                      class="text-right font-mono text-sm tabular-nums text-ink-gray-8"
                    >
                      {{ formatHours(entry.hours) }}
                    </span>
                  </li>
                </ul>
              </section>
            </SectionCard>
          </div>

          <SectionCard
            v-else
            :title="__('Timesheets')"
            :count="listLoading ? undefined : sheets.length"
            :description="
              sheets.length >= LIST_LIMIT
                ? __(
                    'Showing the {0} most recently updated. Narrow the dates, or download the CSV for all of them.',
                    String(LIST_LIMIT)
                  )
                : undefined
            "
            class="mt-3 overflow-hidden"
          >
            <div
              v-if="sheets.length"
              class="hidden gap-4 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5 md:grid"
              :class="GRID"
              aria-hidden="true"
            >
              <span>{{ __("Timesheet") }}</span>
              <span v-if="scope === 'team'">{{ __("Person") }}</span>
              <span>{{ __("Status") }}</span>
              <span class="text-right">{{ __("Hours") }}</span>
              <span class="text-right">{{ __("Updated") }}</span>
            </div>

            <!-- Loading -->
            <div v-if="listLoading" :aria-label="__('Loading')">
              <div
                v-for="i in 5"
                :key="i"
                class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
              >
                <div class="flex flex-1 flex-col gap-2">
                  <div
                    class="h-3.5 w-2/5 animate-pulse rounded bg-surface-gray-2"
                  />
                  <div
                    class="h-3 w-1/4 animate-pulse rounded bg-surface-gray-2"
                  />
                </div>
                <div class="h-3 w-10 animate-pulse rounded bg-surface-gray-2" />
              </div>
            </div>

            <!-- Empty: filtered to nothing, or nothing logged yet -->
            <TaskyState
              v-else-if="!sheets.length && hasFilters"
              :icon="LucideSearchX"
              :title="__('No time logged in these dates')"
              :message="__('Try other dates, or clear the filters.')"
            >
              <Button :label="__('Clear filters')" @click="clearFilters" />
            </TaskyState>
            <TaskyState
              v-else-if="!sheets.length"
              :icon="LucideClock"
              :title="
                scope === 'team'
                  ? __('No timesheets on your projects yet')
                  : __('No timesheets yet')
              "
              :message="
                __(
                  'Log time against a project or task, or complete a task on the board to record hours.'
                )
              "
            >
              <Button variant="solid" :label="__('Log time')" @click="openForm">
                <template #prefix>
                  <LucidePlus class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </TaskyState>

            <ul v-else role="list">
              <li
                v-for="ts in sheets"
                :key="ts.name"
                class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
                :class="GRID"
              >
                <div class="min-w-0">
                  <div class="truncate text-sm text-ink-gray-9">
                    {{ ts.title || ts.name }}
                  </div>
                  <div
                    class="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-ink-gray-5"
                  >
                    <span class="font-mono">{{ ts.name }}</span>
                    <template v-if="ts.project_name || ts.projects?.length">
                      <span aria-hidden="true">·</span>
                      <span class="truncate">{{
                        ts.project_name || ts.projects[0]
                      }}</span>
                    </template>
                    <!-- on small screens the columns fold into this line -->
                    <template v-if="scope === 'team'">
                      <span class="md:hidden" aria-hidden="true">·</span>
                      <span class="text-ink-gray-7 md:hidden">{{
                        ts.owner_name || ts.owner
                      }}</span>
                    </template>
                    <span class="md:hidden" aria-hidden="true">·</span>
                    <span class="md:hidden">{{ __(ts.status) }}</span>
                    <span class="md:hidden" aria-hidden="true">·</span>
                    <span class="tabular-nums md:hidden">{{
                      formatDate(ts.modified)
                    }}</span>
                  </div>
                </div>
                <span
                  v-if="scope === 'team'"
                  class="hidden truncate text-sm text-ink-gray-7 md:block"
                >
                  {{ ts.owner_name || ts.owner }}
                </span>
                <span class="hidden md:block">
                  <TaskyBadge
                    :tone="ts.status === 'Submitted' ? 'success' : 'neutral'"
                    :icon="
                      ts.status === 'Submitted'
                        ? LucideCircleCheck
                        : LucideCircleDashed
                    "
                    :label="__(ts.status)"
                  />
                </span>
                <span
                  class="text-right font-mono text-sm tabular-nums text-ink-gray-8"
                >
                  {{ formatHours(ts.total_hours) }}
                </span>
                <span
                  class="hidden text-right text-sm tabular-nums text-ink-gray-5 md:block"
                >
                  {{ formatDate(ts.modified) }}
                </span>
              </li>
            </ul>
          </SectionCard>
        </template>
      </div>
    </div>

    <Dialog v-model:open="showForm" :title="__('Log time')" size="lg">
      <form
        id="tasky-new-timesheet"
        class="flex flex-col gap-4"
        novalidate
        @submit.prevent="onCreate"
      >
        <TextInput
          v-model="form.title"
          :label="__('Title')"
          :placeholder="__('e.g. Weekly meeting, Bug fix…')"
          required
        />
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormControl
            v-model="form.project"
            type="select"
            :label="__('Project')"
            :options="projectOptions"
          />
          <FormControl
            v-model="form.task"
            type="select"
            :label="__('Task (optional)')"
            :options="taskOptions"
            :disabled="!form.project || taskResource.loading"
          />
          <TextInput
            v-model.number="form.hours"
            type="number"
            step="0.25"
            min="0.25"
            :label="__('Hours')"
          />
          <TextInput v-model="form.notes" :label="__('Notes')" />
        </div>
        <FormControl
          v-model="form.billable"
          type="checkbox"
          :label="__('Billable')"
          :description="
            __(
              'Counts against the customer\'s support hours. Turn off for internal work.'
            )
          "
        />
        <div
          v-if="createTs.error"
          role="alert"
          class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
        >
          <LucideCircleAlert
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          {{ errorText(createTs.error, __("Couldn't create the timesheet.")) }}
        </div>
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            type="submit"
            form="tasky-new-timesheet"
            :label="__('Create timesheet')"
            :loading="createTs.loading"
            :disabled="!form.title.trim()"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import SectionCard from "@/components/SectionCard.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  Dialog,
  FormControl,
  TabButtons,
  TextInput,
  createResource,
  dayjs,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideClock from "~icons/lucide/clock";
import LucideDownload from "~icons/lucide/download";
import LucideFileClock from "~icons/lucide/file-clock";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSearchX from "~icons/lucide/search-x";
import LucideTimer from "~icons/lucide/timer";
import LucideX from "~icons/lucide/x";

interface TimesheetRow {
  name: string;
  title?: string;
  status: string;
  total_hours: number;
  modified: string;
  owner: string;
  owner_name?: string;
  projects?: string[];
  project_name?: string;
}

interface Summary {
  hours: number;
  people: { user: string; full_name: string; hours: number }[];
  projects: {
    project: string | null;
    project_name: string | null;
    hours: number;
  }[];
}

interface DayEntry {
  project: string | null;
  project_name: string | null;
  task: string | null;
  task_subject: string | null;
  hours: number;
  notes: string[];
}

interface Day {
  date: string;
  hours: number;
  entries: DayEntry[];
}

interface PersonDays {
  user: string;
  full_name: string;
  hours: number;
  days: Day[];
}

interface TimesheetDays {
  from_date: string;
  to_date: string;
  too_many: boolean;
  hours: number | null;
  people: PersonDays[];
}

const LIST_LIMIT = 500;
// the most days the By day view shows at once; get_timesheet_days refuses more
const MAX_DAYS = 62;
const BREAKDOWN_ROWS = 6;

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const canSeeTeam = computed(() => authStore.canSeeOverview);

function queryValue(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}

const SCOPES = [
  { key: "mine", label: __("Mine") },
  { key: "team", label: __("Team") },
] as const;
const scope = ref<"mine" | "team">(
  canSeeTeam.value && queryValue("scope") === "team" ? "team" : "mine"
);

const VIEWS = [
  { key: "list", label: __("List") },
  { key: "day", label: __("By day") },
] as const;
const view = ref<"list" | "day">(queryValue("view") === "day" ? "day" : "list");

// whose, which project and when live in the URL, so a period can be shared
const filters = reactive({
  agent: queryValue("agent"),
  project: queryValue("project"),
  from_date: queryValue("from"),
  to_date: queryValue("to"),
});

const DATE = "YYYY-MM-DD";
function thisWeek() {
  const today = dayjs();
  const monday = today.subtract((today.day() + 6) % 7, "day");
  return { from: monday.format(DATE), to: monday.add(6, "day").format(DATE) };
}

// By day always shows a period: this week unless dates are picked; true if it set one
function ensureDayRange() {
  if (view.value !== "day" || (filters.from_date && filters.to_date))
    return false;
  if (filters.from_date) {
    filters.to_date = dayjs(filters.from_date).add(6, "day").format(DATE);
  } else if (filters.to_date) {
    filters.from_date = dayjs(filters.to_date).subtract(6, "day").format(DATE);
  } else {
    const week = thisWeek();
    filters.from_date = week.from;
    filters.to_date = week.to;
  }
  return true;
}
ensureDayRange();

const hasFilters = computed(() => {
  const week = thisWeek();
  // in By day, this week is the default, not a filter
  const datesPicked =
    view.value === "day"
      ? filters.from_date !== week.from || filters.to_date !== week.to
      : !!(filters.from_date || filters.to_date);
  return !!(
    (scope.value === "team" && filters.agent) ||
    filters.project ||
    datesPicked
  );
});

const rangeError = computed(() => {
  if (view.value !== "day" || !filters.from_date || !filters.to_date) return "";
  const days = dayjs(filters.to_date).diff(dayjs(filters.from_date), "day") + 1;
  if (days < 1) return __("The From date must be on or before the To date.");
  if (days > MAX_DAYS)
    return __("Pick up to {0} days at a time.", String(MAX_DAYS));
  return "";
});

const GRID = computed(() =>
  scope.value === "team"
    ? "md:grid-cols-[minmax(0,1fr)_minmax(0,10rem)_7rem_5rem_5rem]"
    : "md:grid-cols-[minmax(0,1fr)_7rem_5rem_5rem]"
);

function filterParams() {
  const team = scope.value === "team";
  return {
    team: team ? 1 : 0,
    ...(team && filters.agent ? { agent: filters.agent } : {}),
    ...(filters.project ? { project: filters.project } : {}),
    ...(filters.from_date ? { from_date: filters.from_date } : {}),
    ...(filters.to_date ? { to_date: filters.to_date } : {}),
  };
}

const timesheets = createResource({
  url: "helpdesk.tasky.api.get_my_timesheets",
  makeParams: () => ({ ...filterParams(), limit: LIST_LIMIT }),
  auto: true,
  transform: (d: TimesheetRow[]) => d ?? [],
  onError() {},
});

const summary = createResource({
  url: "helpdesk.tasky.api.get_timesheet_summary",
  makeParams: () => filterParams(),
  auto: true,
  onError() {},
});

const days = createResource({
  url: "helpdesk.tasky.api.get_timesheet_days",
  makeParams: () => filterParams(),
  auto: view.value === "day" && !rangeError.value,
  onError() {},
});

function reload() {
  timesheets.reload();
  summary.reload();
  if (view.value === "day" && !rangeError.value) days.reload();
}

watch([scope, filters, view], () => {
  // filling in this week's dates runs this again with them
  if (ensureDayRange()) return;
  router.replace({
    query: {
      ...route.query,
      scope: scope.value === "team" ? "team" : undefined,
      view: view.value === "day" ? "day" : undefined,
      agent: (scope.value === "team" && filters.agent) || undefined,
      project: filters.project || undefined,
      from: filters.from_date || undefined,
      to: filters.to_date || undefined,
    },
  });
  reload();
});

const dayData = computed(() => days.data as TimesheetDays | undefined);
const dayPeople = computed(() => dayData.value?.people ?? []);
const dayLoading = computed(() => days.loading && !days.data);

function formatDay(date: string) {
  return dayjs(date).format("ddd D MMM");
}

function personLine(person: PersonDays) {
  return person.days.length === 1
    ? __("{0} on 1 day", formatHours(person.hours))
    : __(
        "{0} over {1} days",
        formatHours(person.hours),
        String(person.days.length)
      );
}

function dayLabel(person: PersonDays, day: Day) {
  return scope.value === "team"
    ? `${person.full_name}, ${formatDay(day.date)}`
    : formatDay(day.date);
}

function entryTitle(entry: DayEntry) {
  if (entry.task) return entry.task_subject || entry.task;
  if (entry.project) return entry.project_name || entry.project;
  return __("No project");
}

const sheets = computed<TimesheetRow[]>(() => timesheets.data ?? []);
const listLoading = computed(() => timesheets.loading && !timesheets.data);
const summaryLoading = computed(() => summary.loading && !summary.data);

const sheetCount = computed(() =>
  sheets.value.length >= LIST_LIMIT ? `${LIST_LIMIT}+` : sheets.value.length
);
// counted from the capped list, so it gets the same "+" as the timesheet count
const drafts = computed(
  () => sheets.value.filter((ts) => ts.status === "Draft").length
);
// counted from the capped list, so it gets the same "+" as the timesheet count
const draftCount = computed(() =>
  sheets.value.length >= LIST_LIMIT ? `${drafts.value}+` : drafts.value
);

const periodLabel = computed(() => {
  const fmt = (d: string) => dayjs(d).format("D MMM YYYY");
  const { from_date: from, to_date: to } = filters;
  if (from && to) return `${fmt(from)} – ${fmt(to)}`;
  if (from) return __("Since {0}", fmt(from));
  if (to) return __("Up to {0}", fmt(to));
  return __("All time");
});

interface BreakdownRow {
  key: string;
  label: string;
  hours: number;
}

const breakdowns = computed(() => {
  const data = summary.data as Summary | undefined;
  const projects: BreakdownRow[] = (data?.projects ?? []).map((p) => ({
    key: p.project || "",
    label: p.project ? p.project_name || p.project : __("No project"),
    hours: p.hours,
  }));
  const byProject = {
    key: "project",
    title: __("By project"),
    description: __("Hours from the time logs in these dates."),
    rows: projects,
  };
  if (scope.value !== "team") return [byProject];
  const people: BreakdownRow[] = (data?.people ?? []).map((p) => ({
    key: p.user,
    label: p.full_name,
    hours: p.hours,
  }));
  return [
    {
      key: "person",
      title: __("By person"),
      description: __("Who logged the hours."),
      rows: people,
    },
    byProject,
  ];
});

// bars show each row's share of the period's hours
function share(hours: number) {
  const total = (summary.data as Summary | undefined)?.hours || 0;
  return total ? Math.max((hours / total) * 100, 1) : 0;
}

function moreLabel(rows: BreakdownRow[]) {
  const rest = rows.slice(BREAKDOWN_ROWS);
  const hours = rest.reduce((sum, r) => sum + r.hours, 0);
  return __("{0} more · {1}", String(rest.length), formatHours(hours));
}

const agents = createResource({
  url: "helpdesk.tasky.api.get_timesheet_agents",
  transform: (d: { user: string; full_name: string }[]) => d ?? [],
  onError() {},
});
watch(
  scope,
  (value) => {
    if (value === "team" && !agents.data) agents.reload();
  },
  { immediate: true }
);
const agentOptions = computed(() => [
  { label: __("All agents"), value: "" },
  ...(agents.data ?? []).map((a: { user: string; full_name: string }) => ({
    label: a.full_name,
    value: a.user,
  })),
]);

function clearFilters() {
  Object.assign(filters, {
    agent: "",
    project: "",
    from_date: "",
    to_date: "",
  });
}

function downloadCsv() {
  const params = new URLSearchParams(
    Object.entries(filterParams()).map(([k, v]) => [k, String(v)])
  );
  window.open(
    `/api/method/helpdesk.tasky.api.export_timesheets_csv?${params}`,
    "_blank"
  );
}

// --- log time ---

const showForm = ref(false);

const form = reactive({
  title: "",
  project: "",
  task: "",
  hours: 1,
  notes: "",
  billable: true,
});

const projectList = createResource({
  url: "helpdesk.tasky.api.get_projects",
  auto: true,
  transform: (d: any[]) => d ?? [],
});

const taskResource = createResource({
  url: "helpdesk.tasky.api.get_project_tasks",
  auto: false,
  transform: (d: any[]) => d ?? [],
});

const taskList = computed(() => taskResource.data ?? []);

const projectChoices = computed(() =>
  (projectList.data ?? []).map((p: any) => ({
    label: p.project_name || p.name,
    value: p.name,
  }))
);
const projectFilterOptions = computed(() => [
  { label: __("All projects"), value: "" },
  ...projectChoices.value,
]);
const projectOptions = computed(() => [
  { label: __("None"), value: "" },
  ...projectChoices.value,
]);

const taskOptions = computed(() => [
  {
    label: taskResource.loading ? __("Loading tasks…") : __("None"),
    value: "",
  },
  ...taskList.value.map((t: any) => ({ label: t.subject, value: t.name })),
]);

watch(
  () => form.project,
  (val) => {
    form.task = "";
    if (val) {
      taskResource.submit({ project: val });
    }
  }
);

const createTs = createResource({
  url: "helpdesk.tasky.api.create_timesheet",
  onSuccess() {
    toast.success(__("Timesheet created"));
    resetForm();
    showForm.value = false;
    reload();
  },
  // shown inline in the dialog
  onError() {},
});

function resetForm() {
  form.title = "";
  form.project = "";
  form.task = "";
  form.hours = 1;
  form.notes = "";
  form.billable = true;
}

function openForm() {
  createTs.reset();
  showForm.value = true;
}

function onCreate() {
  if (!form.title.trim() || createTs.loading) return;
  createTs.submit({
    title: form.title.trim(),
    project: form.project || null,
    task: form.task || null,
    hours: form.hours || 1,
    notes: form.notes,
    billable: form.billable ? 1 : 0,
  });
}

function formatHours(h: number | string | null | undefined) {
  const n = Number(h) || 0;
  return `${Math.round(n * 100) / 100}h`;
}

function formatDate(d: string) {
  return d ? dayjs(d).format("D MMM") : "—";
}
</script>
