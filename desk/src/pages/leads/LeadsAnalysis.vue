<template>
  <!-- how well each person calls, and which kinds of lead pick up -->
  <div class="flex flex-col gap-5">
    <section class="panel" :aria-labelledby="ids.calling" :aria-busy="loading">
      <header class="panel-head">
        <h2 :id="ids.calling" class="text-base-medium text-ink-gray-9">
          {{ __("Calling performance") }}
        </h2>
        <span class="text-xs text-ink-gray-6">{{
          __("Calls from the daily lists and the call log, this period")
        }}</span>
      </header>

      <div
        v-if="!analysis"
        role="alert"
        class="flex flex-wrap items-center gap-3 px-4 py-4"
      >
        <LucideCircleAlert
          class="size-4 shrink-0 text-danger"
          aria-hidden="true"
        />
        <p class="min-w-0 flex-1 text-p-sm text-ink-gray-8">
          {{
            __(
              "Couldn't load the calling figures: {0}",
              errorText(error, __("Check your connection."))
            )
          }}
        </p>
        <Button :label="__('Try again')" @click="emit('retry')" />
      </div>
      <p
        v-else-if="!calling.length"
        class="px-4 py-4 text-p-sm text-ink-gray-6"
      >
        {{
          __(
            "No calls were handed out or logged in this period. Pick a longer period to see more."
          )
        }}
      </p>
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[44rem] text-sm">
          <thead>
            <tr class="text-left text-xs text-ink-gray-6">
              <th scope="col" class="px-4 py-2 font-normal">
                {{ __("Person") }}
              </th>
              <th
                v-for="col in CALLING_COLUMNS"
                :key="col.key"
                scope="col"
                class="px-3 py-2 text-right font-normal"
                :title="col.hint"
              >
                {{ col.label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in calling"
              :key="row.user"
              class="border-t border-outline-gray-1"
            >
              <th
                scope="row"
                class="max-w-[12rem] truncate px-4 py-2 text-left font-normal text-ink-gray-9"
              >
                {{ row.full_name }}
              </th>
              <td
                v-for="col in CALLING_COLUMNS"
                :key="col.key"
                class="px-3 py-2 text-right font-mono tabular-nums"
                :class="
                  col.key === 'overdue' && row.overdue
                    ? 'text-danger'
                    : 'text-ink-gray-9'
                "
              >
                {{ col.format(row) }}
              </td>
            </tr>
          </tbody>
        </table>
        <p
          class="border-t border-outline-gray-1 px-4 py-2 text-xs text-ink-gray-6"
        >
          {{
            __(
              "Given: leads on the daily call lists. Done: share of those called. Reached: the person picked up. Overdue: not called when the list ended."
            )
          }}
        </p>
      </div>
    </section>

    <section
      v-if="analysis && groups.length"
      class="panel"
      :aria-labelledby="ids.quality"
      :aria-busy="loading"
    >
      <header class="panel-head">
        <h2 :id="ids.quality" class="text-base-medium text-ink-gray-9">
          {{ __("Lead quality") }}
        </h2>
        <span class="text-xs text-ink-gray-6">{{
          __("Leads that came in during this period")
        }}</span>
      </header>
      <div class="flex flex-col gap-3 px-4 pt-3">
        <div class="overflow-x-auto">
          <TabButtons
            :model-value="group"
            size="sm"
            :aria-label="__('Group leads by')"
            :options="groups"
            @update:model-value="group = $event as QualityGroup"
          />
        </div>
        <p v-if="verdict" class="text-p-sm text-ink-gray-8">{{ verdict }}</p>
      </div>

      <p v-if="!rows.length" class="px-4 py-4 text-p-sm text-ink-gray-6">
        {{ __("No leads came in during this period.") }}
      </p>
      <div v-else class="mt-3 overflow-x-auto">
        <table class="w-full min-w-[40rem] text-sm">
          <thead>
            <tr class="text-left text-xs text-ink-gray-6">
              <th scope="col" class="px-4 py-2 font-normal">
                {{ groupLabel }}
              </th>
              <th
                v-for="col in QUALITY_COLUMNS"
                :key="col.key"
                scope="col"
                class="px-3 py-2 text-right font-normal"
                :title="col.hint"
              >
                {{ col.label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.value || '-'"
              class="border-t border-outline-gray-1"
            >
              <th
                scope="row"
                class="max-w-[14rem] px-4 py-2 text-left font-normal"
              >
                <span
                  class="block truncate"
                  :class="row.value ? 'text-ink-gray-9' : 'text-ink-gray-6'"
                  >{{ row.value || __("Not set") }}</span
                >
                <span
                  v-if="row.value && row.value === best"
                  class="inline-flex items-center gap-1 text-xs text-success"
                >
                  <LucideArrowUp class="size-3" aria-hidden="true" />
                  {{ __("Picks up most") }}
                </span>
                <span
                  v-else-if="row.value && row.value === worst"
                  class="inline-flex items-center gap-1 text-xs text-danger"
                >
                  <LucideArrowDown class="size-3" aria-hidden="true" />
                  {{ __("Picks up least") }}
                </span>
              </th>
              <td
                v-for="col in QUALITY_COLUMNS"
                :key="col.key"
                class="px-3 py-2 text-right font-mono tabular-nums text-ink-gray-9"
              >
                {{ col.format(row) }}
              </td>
            </tr>
          </tbody>
        </table>
        <p
          class="border-t border-outline-gray-1 px-4 py-2 text-xs text-ink-gray-6"
        >
          {{
            __(
              "Called, wrong number and not interested are shares of the leads. Picked up is the share of called leads who answered. Moved on: reached a meeting or further."
            )
          }}
        </p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, TabButtons } from "frappe-ui";
import { computed, ref, useId } from "vue";
import LucideArrowDown from "~icons/lucide/arrow-down";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import type {
  CallingRow,
  LeadAnalysis,
  QualityGroup,
  QualityRow,
} from "./leads";

const props = defineProps<{
  analysis?: LeadAnalysis | undefined;
  error?: { message: string } | undefined;
  loading?: boolean | undefined;
}>();
const emit = defineEmits<{ retry: [] }>();

const GROUPS: { value: QualityGroup; label: string }[] = [
  { value: "source", label: __("Source") },
  { value: "industry", label: __("Industry") },
  { value: "district", label: __("District") },
  { value: "department", label: __("Department") },
  { value: "product", label: __("Product") },
];

function percent(value: number) {
  return `${Math.round(value)}%`;
}

function talkTime(seconds: number) {
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return __("{0}m", String(minutes));
  return __(
    "{0}h {1}m",
    String(Math.floor(minutes / 60)),
    String(minutes % 60)
  );
}

const CALLING_COLUMNS: {
  key: keyof CallingRow;
  label: string;
  hint: string;
  format: (row: CallingRow) => string;
}[] = [
  {
    key: "given",
    label: __("Given"),
    hint: __("Leads handed out on the daily call lists"),
    format: (row) => String(row.given),
  },
  {
    key: "called",
    label: __("Called"),
    hint: __("Leads called from those lists"),
    format: (row) => String(row.called),
  },
  {
    key: "completion",
    label: __("Done"),
    hint: __("Share of the given leads that were called"),
    format: (row) => (row.given ? percent(row.completion) : "–"),
  },
  {
    key: "reached",
    label: __("Reached"),
    hint: __("Called leads where the person picked up"),
    format: (row) => String(row.reached),
  },
  {
    key: "reach_rate",
    label: __("Reach rate"),
    hint: __("Share of the called leads who picked up"),
    format: (row) => (row.called ? percent(row.reach_rate) : "–"),
  },
  {
    key: "overdue",
    label: __("Overdue"),
    hint: __("Leads not called before their list ended"),
    format: (row) => String(row.overdue),
  },
  {
    key: "calls",
    label: __("Calls"),
    hint: __("Every call in the call log"),
    format: (row) => String(row.calls),
  },
  {
    key: "missed",
    label: __("Missed"),
    hint: __("Calls in the log that nobody answered"),
    format: (row) => String(row.missed),
  },
  {
    key: "talk_seconds",
    label: __("Talk time"),
    hint: __("Time spent talking on answered calls"),
    format: (row) => talkTime(row.talk_seconds),
  },
];

const QUALITY_COLUMNS: {
  key: string;
  label: string;
  hint: string;
  format: (row: QualityRow) => string;
}[] = [
  {
    key: "leads",
    label: __("Leads"),
    hint: __("Leads that came in during this period"),
    format: (row) => String(row.leads),
  },
  {
    key: "called",
    label: __("Called"),
    hint: __("Share of the leads that were called"),
    format: (row) => percent(row.called_rate),
  },
  {
    key: "reach",
    label: __("Picked up"),
    hint: __("Share of the called leads who picked up"),
    format: (row) => (row.called ? percent(row.reach_rate) : "–"),
  },
  {
    key: "wrong",
    label: __("Wrong number"),
    hint: __("Share of the leads with a wrong number"),
    format: (row) => percent(row.wrong_rate),
  },
  {
    key: "declined",
    label: __("Not interested"),
    hint: __("Share of the leads who said no"),
    format: (row) => percent(row.not_interested_rate),
  },
  {
    key: "moved",
    label: __("Moved on"),
    hint: __("Leads that reached a meeting, a proposal or a win"),
    format: (row) => String(row.moved_on),
  },
  {
    key: "won",
    label: __("Won"),
    hint: __("Leads now won"),
    format: (row) => String(row.won),
  },
];

const ids = { calling: useId(), quality: useId() };
const calling = computed(() => props.analysis?.calling ?? []);
const groups = computed(() =>
  GROUPS.filter((g) => props.analysis?.quality?.[g.value])
);
const chosen = ref<QualityGroup>("source");
// the site may not have the chosen field: fall back to the first it has
const group = computed({
  get: () =>
    groups.value.some((g) => g.value === chosen.value)
      ? chosen.value
      : groups.value[0]?.value ?? "source",
  set: (value: QualityGroup) => (chosen.value = value),
});
const groupLabel = computed(
  () => GROUPS.find((g) => g.value === group.value)?.label ?? ""
);
const current = computed(() => props.analysis?.quality?.[group.value]);
const rows = computed(() => current.value?.rows ?? []);
const best = computed(() => current.value?.best);
const worst = computed(() => current.value?.worst);

const verdict = computed(() => {
  const top = rows.value.find((r) => r.value === best.value);
  const bottom = rows.value.find((r) => r.value === worst.value);
  if (!top || !bottom) return "";
  return __(
    "{0} picks up most ({1} of called leads). {2} picks up least ({3}).",
    top.value!,
    percent(top.reach_rate),
    bottom.value!,
    percent(bottom.reach_rate)
  );
});
</script>

<style scoped>
.panel {
  @apply min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base;
}
.panel-head {
  @apply flex flex-wrap items-baseline justify-between gap-2 border-b border-outline-gray-1 px-4 py-3;
}
</style>
