<template>
  <div class="flex flex-col gap-4">
    <!-- the day and whose report: kept in the URL, so a view can be shared -->
    <div
      class="flex flex-wrap items-end gap-3"
      role="group"
      :aria-label="__('Day and salesperson')"
    >
      <div class="flex items-end gap-1">
        <Button
          :aria-label="__('Previous day')"
          :tooltip="__('Previous day')"
          @click="shift(-1)"
        >
          <template #icon>
            <LucideChevronLeft class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <FormControl
          v-model="date"
          type="date"
          class="w-40"
          :label="__('Day')"
          :max="todayIso"
        />
        <Button
          :aria-label="__('Next day')"
          :tooltip="__('Next day')"
          :disabled="date >= todayIso"
          @click="shift(1)"
        >
          <template #icon>
            <LucideChevronRight class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-if="date !== todayIso"
          :label="__('Today')"
          @click="date = todayIso"
        />
      </div>
      <FormControl
        v-if="roster.length > 1"
        v-model="person"
        type="select"
        class="w-full sm:w-56"
        :label="__('Salesperson')"
        :options="personOptions"
      />
      <Button
        v-if="showTeam && people.length"
        class="sm:ml-auto"
        :label="__('Copy team report')"
        @click="copy(data!.team_text || '', __('Team report copied'))"
      >
        <template #prefix>
          <LucideCopy class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>

    <TaskyState
      v-if="report.error && !data"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the daily report')"
      :message="
        errorText(report.error, __('Check your connection and try again.'))
      "
    >
      <Button :label="__('Try again')" @click="reload()" />
    </TaskyState>

    <div
      v-else-if="!data"
      class="flex flex-col gap-4"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div class="h-40 animate-pulse rounded-xl bg-surface-gray-2" />
      <div class="h-40 animate-pulse rounded-xl bg-surface-gray-2" />
    </div>

    <TaskyState
      v-else-if="!data.available"
      :icon="LucideCalendarX"
      :title="__('The daily report isn\'t available yet')"
      :message="__('The ERP site needs the latest TBO Smart.')"
    />

    <template v-else>
      <!-- a failed update keeps the last numbers, and says so -->
      <div
        v-if="report.error"
        role="alert"
        class="flex flex-wrap items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3"
      >
        <LucideCircleAlert
          class="size-4 shrink-0 text-danger"
          aria-hidden="true"
        />
        <p class="min-w-0 flex-1 text-p-sm text-ink-gray-8">
          {{
            __(
              "Couldn't update the report: {0} These numbers may be out of date.",
              errorText(report.error, __("Check your connection."))
            )
          }}
        </p>
        <Button :label="__('Try again')" @click="reload()" />
      </div>
      <span v-if="report.loading" class="sr-only" aria-live="polite">{{
        __("Updating")
      }}</span>

      <TaskyState
        v-if="!people.length"
        :icon="LucideUsers"
        :title="__('No salespeople in your view')"
        :message="
          data?.team_empty && authStore.isManager
            ? __(
                'Pick your salespeople in Settings → Agents → Department wall → Sales team'
              )
            : __('Nobody on the ERP site has leads you may see for this day.')
        "
      />

      <!-- the team: one row each, a tap opens the person -->
      <section
        v-else-if="showTeam"
        :aria-labelledby="ids.team"
        class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
      >
        <h2 :id="ids.team" class="sr-only">
          {{
            __(
              "Daily sales performance · {0}",
              dayjs(date).format("D MMM YYYY")
            )
          }}
        </h2>
        <div class="row row-head hidden md:grid" aria-hidden="true">
          <span>{{ __("Salesperson") }}</span>
          <span v-for="col in COLUMNS" :key="col.key" class="text-right">{{
            col.label
          }}</span>
          <span>{{ __("This week") }}</span>
        </div>
        <ul role="list" class="divide-y divide-outline-gray-1">
          <li v-for="p in people" :key="p.user">
            <button
              type="button"
              class="row w-full text-left transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
              :aria-label="__('Open {0}\'s report', p.full_name)"
              @click="person = p.user"
            >
              <span
                class="col-span-2 truncate text-sm-medium text-ink-gray-9 md:col-span-1"
                >{{ p.full_name }}</span
              >
              <span
                v-for="col in COLUMNS"
                :key="col.key"
                class="flex flex-col md:items-end"
              >
                <span class="text-2xs text-ink-gray-6 md:hidden">{{
                  col.label
                }}</span>
                <span
                  class="font-mono text-sm tabular-nums"
                  :class="col.tone"
                  >{{ col.value(p) }}</span
                >
                <span
                  v-if="col.sub"
                  class="font-mono text-2xs tabular-nums text-ink-gray-6"
                  >{{ col.sub(p) }}</span
                >
              </span>
              <span class="col-span-2 flex flex-wrap gap-1 md:col-span-1">
                <span
                  v-if="p.on_track && hasTargets"
                  class="chip"
                  :class="TONE_CLASSES.success"
                >
                  <LucideCircleCheck class="size-3.5" aria-hidden="true" />
                  {{ __("On track") }}
                </span>
                <span
                  v-for="b in p.behind"
                  :key="b.metric"
                  class="chip"
                  :class="TONE_CLASSES.warning"
                >
                  <LucideClock class="size-3.5" aria-hidden="true" />
                  {{ __("Behind by {0} {1}", String(b.by), UNITS[b.metric]) }}
                </span>
              </span>
            </button>
          </li>
        </ul>
      </section>

      <template v-else>
        <div v-if="roster.length > 1" class="flex">
          <Button
            variant="ghost"
            :label="__('All salespeople')"
            @click="person = ''"
          >
            <template #prefix>
              <LucideChevronLeft class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
        <DailyReportCard
          v-for="p in people"
          :key="p.user"
          :person="p"
          :date="data.date || date"
          :currency="data.currency || 'INR'"
          :days="data.working_days"
          @copy="copy($event, __('Report copied'))"
        />
      </template>

      <!-- who was handed how many calls, and how many they made -->
      <CallBatchesTable v-if="showTeam" ref="batchesTable" :date="date" />
    </template>

    <!-- when the browser won't let the page copy: the text, ready to select -->
    <Dialog
      :open="showFallback"
      :title="__('Copy the report')"
      size="lg"
      @update:open="(value: boolean) => (showFallback = value)"
    >
      <p class="mb-2 text-p-sm text-ink-gray-7">
        {{
          __("Your browser didn't allow copying. Select the text and copy it.")
        }}
      </p>
      <textarea
        ref="fallbackField"
        readonly
        rows="14"
        class="w-full rounded-md border border-outline-gray-2 bg-surface-base p-2 font-mono text-sm text-ink-gray-9"
        :value="fallbackText"
        :aria-label="__('Report text')"
        @focus="($event.target as HTMLTextAreaElement).select()"
      />
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { money } from "@/components/invoicing/invoices";
import TaskyState from "@/components/TaskyState.vue";
import { TONE_CLASSES } from "@/components/tone";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  dayjs,
  Dialog,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, nextTick, ref, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCalendarX from "~icons/lucide/calendar-x";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideCopy from "~icons/lucide/copy";
import LucideUsers from "~icons/lucide/users";
import CallBatchesTable from "./CallBatchesTable.vue";
import DailyReportCard from "./DailyReportCard.vue";
import {
  copyText,
  leadOptions,
  ownerName,
  type DailyMetric,
  type DailyPerson,
  type DailyReport,
  type LeadOptions,
} from "./leads";

const DAY = "YYYY-MM-DD";
const UNITS: Record<DailyMetric, string> = {
  leads: __("leads"),
  meetings: __("meetings"),
  proposals: __("proposals"),
  follow_ups: __("follow-ups"),
};
// each tone says what the number is: calls info, positive success, quotations warning
const COLUMNS: {
  key: string;
  label: string;
  tone: string;
  value: (p: DailyPerson) => string | number;
  sub?: (p: DailyPerson) => string;
}[] = [
  {
    key: "calls",
    label: __("Calls"),
    tone: "text-info",
    value: (p) => p.calls_total,
    sub: (p) => __("{0} connected", String(p.calls_connected)),
  },
  {
    key: "fresh",
    label: __("Fresh"),
    tone: "text-ink-gray-9",
    value: (p) => p.fresh_leads,
  },
  {
    key: "follow",
    label: __("Follow-up"),
    tone: "text-ink-gray-9",
    value: (p) => p.follow_up_leads,
  },
  {
    key: "positive",
    label: __("Positive"),
    tone: "text-success",
    value: (p) => p.positive_leads.length,
  },
  {
    key: "quotes",
    label: __("Quotations"),
    tone: "text-warning",
    value: (p) => p.new_quotations.count,
    sub: (p) => money(p.new_quotations.value, currency.value, true),
  },
  {
    key: "new",
    label: __("New leads"),
    tone: "text-brand-ink",
    value: (p) => p.new_leads.length,
  },
];

const route = useRoute();
const router = useRouter();
const ids = { team: useId() };

const todayIso = dayjs().format(DAY);
function queryText(key: string) {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}
const queryDate = queryText("date");
const date = ref(
  dayjs(queryDate, DAY, true).isValid() && queryDate <= todayIso
    ? queryDate
    : todayIso
);
const person = ref(queryText("person"));

let fresh = 0;
const report = createResource({
  url: "helpdesk.api.leads.get_daily_report",
  makeParams: () => ({
    date: date.value,
    owner: person.value || null,
    fresh,
  }),
  auto: true,
});

const data = computed(() => report.data as DailyReport | undefined);
const authStore = useAuthStore();
const people = computed(() => data.value?.people ?? []);
const currency = computed(() => data.value?.currency || "INR");
const hasTargets = computed(() =>
  Object.values(data.value?.targets ?? {}).some(Boolean)
);

// the people of the last whole-team read, for the picker (a person's own read lists one)
const team = ref<{ user: string; full_name: string }[]>([]);
watch(data, (d) => {
  if (d?.available && !person.value)
    team.value = (d.people ?? []).map((p) => ({
      user: p.user,
      full_name: p.full_name,
    }));
});
const roster = computed(() => {
  const found = [...team.value];
  const options = leadOptions.data as LeadOptions | undefined;
  if (person.value && !found.some((p) => p.user === person.value))
    found.push({
      user: person.value,
      full_name: ownerName(options, person.value),
    });
  return found;
});
const personOptions = computed(() => [
  { label: __("Everyone"), value: "" },
  ...roster.value.map((p) => ({ label: p.full_name, value: p.user })),
]);
// no one picked and more than one in view: the team; a salesperson sees their own card
const batchesTable = ref<InstanceType<typeof CallBatchesTable> | null>(null);
const showTeam = computed(() => !person.value && people.value.length > 1);

function shift(days: number) {
  const next = dayjs(date.value).add(days, "day").format(DAY);
  if (next <= todayIso) date.value = next;
}

function reload() {
  fresh = 1;
  report.reload();
  fresh = 0;
  batchesTable.value?.reload();
}
defineExpose({ reload });

watch([date, person], ([day, owner]) => {
  router.replace({
    query: {
      ...route.query,
      date: day === todayIso ? undefined : day,
      person: owner || undefined,
    },
  });
  report.reload();
});

// --- copying ---

const showFallback = ref(false);
const fallbackText = ref("");
const fallbackField = ref<HTMLTextAreaElement | null>(null);

async function copy(text: string, done: string) {
  if (await copyText(text)) {
    toast.success(done);
    return;
  }
  fallbackText.value = text;
  showFallback.value = true;
  await nextTick();
  fallbackField.value?.select();
}
</script>

<style scoped>
.row {
  @apply grid grid-cols-2 items-start gap-x-3 gap-y-2 px-4 py-3;
}
.row-head {
  @apply items-center border-b border-outline-gray-1 bg-surface-gray-1 py-2 text-xs text-ink-gray-6;
}
.chip {
  @apply inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs;
}
@media (min-width: 768px) {
  .row {
    grid-template-columns:
      minmax(9rem, 1.6fr) repeat(6, minmax(3.5rem, 1fr))
      minmax(10rem, 1.8fr);
  }
}
</style>
