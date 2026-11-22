<template>
  <!-- everyone's month side by side: one row a person, one column a target, each cell what they
       achieved of it, coloured by where they stand against today's pace -->
  <section
    class="min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-labelledby="headingId"
  >
    <div
      class="flex flex-wrap items-start justify-between gap-3 border-b border-outline-gray-2 p-4 md:px-5"
    >
      <div class="flex min-w-0 flex-col gap-0.5">
        <h2 :id="headingId" class="text-base font-semibold text-ink-gray-9">
          {{ __("Everyone's targets") }}
        </h2>
        <p class="text-sm text-ink-gray-6">
          {{
            __(
              "Each cell is one target: achieved of goal, coloured by pace for today."
            )
          }}
        </p>
      </div>
      <ViewTabs
        :model-value="filter"
        :aria-label="__('Who to show')"
        :options="filterOptions"
        @update:model-value="emit('update:filter', $event as TeamFilter)"
      />
      <ul
        class="flex w-full flex-wrap gap-x-4 gap-y-1 text-xs font-medium text-ink-gray-7"
        :aria-label="__('Key')"
      >
        <li
          v-for="item in LEGEND"
          :key="item.label"
          class="flex items-center gap-1.5"
        >
          <span
            class="size-3 shrink-0 rounded-[3px] border-[1.5px]"
            :class="item.swatch"
            aria-hidden="true"
          />
          {{ item.label }}
        </li>
      </ul>
    </div>

    <TaskyState
      v-if="!rows.length"
      class="py-10"
      :icon="filter === 'behind' ? LucideCircleCheck : LucideUsers"
      :title="
        filter === 'behind'
          ? __('No one is behind pace')
          : __('No one to show here')
      "
      :message="__('Show everyone to see the whole team.')"
    >
      <Button
        :label="__('Show everyone')"
        @click="emit('update:filter', 'all')"
      />
    </TaskyState>

    <div v-else class="overflow-x-auto">
      <table class="w-full border-separate border-spacing-0 text-left">
        <thead>
          <tr
            class="text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6"
          >
            <th
              scope="col"
              class="sticky left-0 z-10 h-11 min-w-[13rem] border-b border-outline-gray-1 bg-surface-base pl-4 pr-3 md:pl-5"
            >
              {{ __("Person") }}
            </th>
            <th
              v-for="column in columns"
              :key="column.criterion"
              scope="col"
              class="h-11 min-w-[7.5rem] border-b border-outline-gray-1 px-1.5 last:pr-4"
            >
              <span class="block truncate" :title="column.criterion">{{
                column.criterion
              }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.person.user">
            <th
              scope="row"
              class="sticky left-0 z-10 border-b border-outline-gray-1 bg-surface-base py-2.5 pl-4 pr-3 font-normal md:pl-5"
            >
              <button
                type="button"
                class="flex w-full min-w-0 items-center gap-3 rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                :title="__('Open {0}\'s targets', row.person.full_name)"
                @click="emit('open', row.person.user)"
              >
                <PersonAvatar :name="row.person.full_name" size="lg" />
                <span class="flex min-w-0 flex-col">
                  <span
                    class="truncate text-sm font-semibold text-ink-gray-9 hover:underline"
                    >{{ row.person.full_name }}</span
                  >
                  <span
                    class="truncate text-xs tabular-nums"
                    :class="
                      row.standing === 'behind'
                        ? 'font-medium text-warning'
                        : 'text-ink-gray-6'
                    "
                    >{{ personLine(row) }}</span
                  >
                </span>
              </button>
            </th>

            <td
              v-if="!row.person.target"
              :colspan="Math.max(columns.length, 1)"
              class="border-b border-outline-gray-1 py-2.5 pl-1.5 pr-4"
            >
              <span
                class="flex h-[60px] items-center rounded-lg border border-dashed border-outline-gray-3 px-3.5 text-sm text-ink-gray-6"
              >
                {{ __("No targets for {0} yet", monthTitle(month)) }}
              </span>
            </td>
            <td
              v-for="(cell, i) in cells.get(row.person.user) ?? []"
              :key="columns[i].criterion"
              class="border-b border-outline-gray-1 px-1.5 py-2.5 last:pr-4"
            >
              <span
                v-if="!cell"
                class="flex h-[60px] flex-col justify-center rounded-lg border border-dashed border-outline-gray-2 px-2.5 text-xs text-ink-gray-5"
              >
                <span aria-hidden="true">—</span>
                {{ __("Not a target") }}
              </span>
              <span
                v-else-if="cell.counting"
                class="block h-[60px] animate-pulse rounded-lg bg-surface-gray-2"
                :aria-label="__('Counting')"
              />
              <span
                v-else
                class="relative flex h-[60px] flex-col justify-center gap-0.5 rounded-lg border px-2.5"
                :class="STANDING_LOOK[cell.standing].cell"
                :title="cell.text || undefined"
              >
                <component
                  :is="STANDING_LOOK[cell.standing].icon"
                  v-if="cell.standing !== 'none'"
                  class="absolute right-2 top-2 size-3"
                  :class="STANDING_LOOK[cell.standing].ink"
                  aria-hidden="true"
                />
                <span
                  class="truncate pr-4 font-mono text-sm font-semibold text-ink-gray-9 tabular-nums"
                  >{{ cell.value }}</span
                >
                <span class="truncate text-xs text-ink-gray-6 tabular-nums">{{
                  cell.of
                }}</span>
                <span v-if="cell.text" class="sr-only">{{ cell.text }}</span>
                <span
                  v-if="cell.percent != null"
                  class="mt-1 block h-1 overflow-hidden rounded-full bg-surface-base"
                  aria-hidden="true"
                >
                  <span
                    class="block h-full rounded-full"
                    :class="STANDING_LOOK[cell.standing].fill"
                    :style="{ width: `${Math.min(cell.percent, 100)}%` }"
                  />
                </span>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import PersonAvatar from "@/components/PersonAvatar.vue";
import TaskyState from "@/components/TaskyState.vue";
import ViewTabs from "@/components/ViewTabs.vue";
import { __ } from "@/translation";
import { Button } from "frappe-ui";
import { computed } from "vue";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideUsers from "~icons/lucide/users";
import {
  monthTitle,
  STANDING_LOOK,
  targetCell,
  type Criterion,
  type TeamFilter,
  type TeamRow,
} from "./salesTargets";

const props = defineProps<{
  rows: TeamRow[];
  /** every target given this month, in the order first met */
  columns: Criterion[];
  month: string;
  currency: string;
  filter: TeamFilter;
  filterOptions: { label: string; value: TeamFilter; count: number }[];
  headingId: string;
}>();
const emit = defineEmits<{
  open: [user: string];
  "update:filter": [value: TeamFilter];
}>();

// the swatches say what each cell colour means; each cell also has an icon and its words
const LEGEND = [
  {
    label: __("Reached"),
    swatch: "border-success bg-success-soft",
  },
  { label: __("On pace"), swatch: "border-info bg-info-soft" },
  { label: __("Behind pace"), swatch: "border-warning bg-warning-soft" },
  {
    label: __("Nothing counted"),
    swatch: "border-outline-gray-3 bg-surface-gray-1",
  },
  { label: __("Not set"), swatch: "border-dashed border-outline-gray-3" },
];

// each person with targets: one cell a column, null where that target isn't theirs
const cells = computed(
  () =>
    new Map(
      props.rows
        .filter((row) => row.person.target)
        .map((row) => [
          row.person.user,
          props.columns.map((column) => {
            const name = column.criterion.toLowerCase();
            const criterion = row.person.target!.criteria.find(
              (c) => c.criterion.toLowerCase() === name
            );
            return criterion
              ? targetCell(criterion, row.progress, props.currency)
              : null;
          }),
        ])
    )
);

function personLine(row: TeamRow) {
  const target = row.person.target;
  if (!target) return __("Not set");
  const count =
    target.criteria.length === 1
      ? __("1 target")
      : __("{0} targets", String(target.criteria.length));
  if (row.overall?.percent != null)
    return row.overall.behind
      ? __(
          "{0}% · {1} of {2} behind",
          String(row.overall.percent),
          String(row.overall.behind),
          String(row.overall.counted)
        )
      : __("{0}% · on track", String(row.overall.percent));
  if (!row.progress) return __("{0} · counting…", count);
  if (row.progress.state === "not_started") return __("{0} · not begun", count);
  if (row.progress.state === "unavailable")
    return __("{0} · couldn't count", count);
  return __("{0} · nothing counted", count);
}
</script>
