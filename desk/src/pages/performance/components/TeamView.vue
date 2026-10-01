<template>
  <div class="flex flex-col gap-4">
    <section
      class="grid grid-cols-2 gap-3 lg:grid-cols-6"
      :aria-label="__('Team summary')"
    >
      <StatTile
        hero
        :icon="LucideClock"
        :label="__('Hours logged')"
        :value="formatHours(data.totals.hours)"
        :sub="
          __(
            'of {0} expected · {1} people',
            formatHours(data.totals.expected_hours),
            String(data.totals.people)
          )
        "
        :meter="data.totals.utilisation"
        :tone="utilTone(data.totals.utilisation)"
      />
      <StatTile
        :icon="LucideGauge"
        :label="__('Utilisation')"
        :value="pctText(data.totals.utilisation)"
        :sub="__('logged ÷ working hours so far')"
      />
      <StatTile
        :icon="LucideCircleCheck"
        :label="__('Tasks completed')"
        :value="String(data.totals.tasks_completed)"
        :sub="
          data.totals.on_time_pct == null
            ? __('none completed')
            : __('{0} on time', pctText(data.totals.on_time_pct))
        "
      />
      <StatTile
        :icon="LucideCircleAlert"
        :label="__('Overdue tasks')"
        :value="String(data.totals.tasks_overdue)"
        :sub="__('open and past their due date')"
      />
      <StatTile
        :icon="LucideSend"
        :label="__('Posts published')"
        :value="String(data.totals.posts_published)"
        :sub="__('{0} missed', String(data.totals.posts_missed))"
      />
    </section>

    <section
      class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
    >
      <h2 class="text-base font-semibold text-ink-gray-9">
        {{ __("Team hours per day") }}
      </h2>
      <p class="mb-2 text-p-sm text-ink-gray-5">
        {{ __("Everyone's logged time added up") }}
      </p>
      <DailyHoursChart :days="data.daily" />
    </section>
    <section
      class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
    >
      <header class="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 class="text-base font-semibold text-ink-gray-9">
            {{ __("Hours by person") }}
          </h2>
          <p class="text-p-sm text-ink-gray-5">
            {{ __("Split by activity. Click a person for their report.") }}
          </p>
        </div>
        <ul
          class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-gray-6"
          :aria-label="__('Activities')"
        >
          <li
            v-for="(a, i) in data.activities"
            :key="a"
            class="flex items-center gap-1.5"
          >
            <span
              class="size-2.5 rounded-sm"
              :style="{ background: colors.series[i] }"
              aria-hidden="true"
            />{{ a }}
          </li>
          <li class="flex items-center gap-1.5">
            <span
              class="size-2.5 rounded-sm"
              :style="{ background: colors.other }"
              aria-hidden="true"
            />{{ __("Other") }}
          </li>
        </ul>
      </header>
      <p
        v-if="!charted.length"
        class="py-10 text-center text-p-sm text-ink-gray-5"
      >
        {{ __("No one logged time in this period.") }}
      </p>
      <HoursByPersonChart
        v-else
        :rows="charted"
        :activities="data.activities"
        @select="emit('select', $event)"
      />
    </section>

    <section
      class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
    >
      <header class="flex items-baseline justify-between gap-2 px-4 pt-4">
        <h2 class="text-base font-semibold text-ink-gray-9">
          {{ __("Everyone") }}
        </h2>
        <span v-if="data.totals.idle_people" class="text-p-sm text-ink-gray-5">
          {{
            __(
              "{0} people with no time, tasks or posts in this period are hidden",
              String(data.totals.idle_people)
            )
          }}
        </span>
      </header>
      <div class="overflow-x-auto">
        <table class="mt-2 w-full min-w-[920px] text-left text-sm">
          <thead
            class="border-y border-outline-gray-2 bg-surface-gray-1 text-xs text-ink-gray-5"
          >
            <tr>
              <th scope="col" class="px-4 py-2 font-medium">
                {{ __("Employee") }}
              </th>
              <th scope="col" class="px-4 py-2 font-medium">
                {{ __("Hours vs expected") }}
              </th>
              <th scope="col" class="px-4 py-2 text-right font-medium">
                {{ __("Active days") }}
              </th>
              <th scope="col" class="px-4 py-2 text-right font-medium">
                {{ __("Tasks done") }}
              </th>
              <th scope="col" class="px-4 py-2 text-right font-medium">
                {{ __("On time") }}
              </th>
              <th scope="col" class="px-4 py-2 text-right font-medium">
                {{ __("Overdue") }}
              </th>
              <th scope="col" class="px-4 py-2 text-right font-medium">
                {{ __("Posts published") }}
              </th>
              <th scope="col" class="px-4 py-2 text-right font-medium">
                {{ __("Posts missed") }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="r in data.rows"
              :key="r.employee"
              class="cursor-pointer border-b border-outline-gray-1 last:border-0 hover:bg-surface-gray-1"
              @click="emit('select', r.employee)"
            >
              <td class="px-4 py-2.5">
                <button
                  type="button"
                  class="flex items-center gap-2 text-left"
                  @click.stop="emit('select', r.employee)"
                >
                  <Avatar size="sm" :image="r.image" :label="r.employee_name" />
                  <span class="flex flex-col">
                    <span class="text-ink-gray-9 hover:underline">{{
                      r.employee_name
                    }}</span>
                    <span class="text-xs text-ink-gray-5">{{
                      r.designation || r.department || ""
                    }}</span>
                  </span>
                </button>
              </td>
              <td class="px-4 py-2.5">
                <div class="flex items-center gap-2 whitespace-nowrap">
                  <div
                    class="h-2 w-28 overflow-hidden rounded-full"
                    :class="TRACK[utilTone(r.utilisation)]"
                  >
                    <div
                      class="h-full rounded-full"
                      :class="FILL[utilTone(r.utilisation)]"
                      :style="{
                        width: `${Math.min(r.utilisation || 0, 100)}%`,
                      }"
                    />
                  </div>
                  <span
                    class="font-mono text-xs tabular-nums text-ink-gray-7"
                    >{{ formatHours(r.hours) }}</span
                  >
                  <span class="font-mono text-xs tabular-nums text-ink-gray-5"
                    >/ {{ formatHours(r.expected_hours) }}</span
                  >
                </div>
              </td>
              <td
                class="px-4 py-2.5 text-right font-mono tabular-nums text-ink-gray-7"
              >
                {{ r.active_days }}
              </td>
              <td
                class="px-4 py-2.5 text-right font-mono tabular-nums text-ink-gray-7"
              >
                {{ r.tasks_completed }}
              </td>
              <td
                class="px-4 py-2.5 text-right font-mono tabular-nums text-ink-gray-7"
              >
                {{ pctText(r.on_time_pct) }}
              </td>
              <td
                class="px-4 py-2.5 text-right font-mono tabular-nums"
                :class="r.tasks_overdue ? 'text-danger' : 'text-ink-gray-7'"
              >
                {{ r.tasks_overdue }}
              </td>
              <td
                class="px-4 py-2.5 text-right font-mono tabular-nums text-ink-gray-7"
              >
                {{ r.posts_published }}
              </td>
              <td
                class="px-4 py-2.5 text-right font-mono tabular-nums"
                :class="r.posts_missed ? 'text-danger' : 'text-ink-gray-7'"
              >
                {{ r.posts_missed }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Avatar } from "frappe-ui";
import { computed } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideGauge from "~icons/lucide/gauge";
import LucideSend from "~icons/lucide/send";
import { formatHours, useChartColors } from "../chartTheme";
import { FILL, TRACK, pctText, utilTone } from "../performanceMeta";
import DailyHoursChart from "./DailyHoursChart.vue";
import HoursByPersonChart from "./HoursByPersonChart.vue";
import StatTile from "./StatTile.vue";

const props = defineProps<{ data: any }>();
const emit = defineEmits<{ (e: "select", employee: string): void }>();
const colors = useChartColors();
// people with no logged time stay in the table but would only be empty rows here
const charted = computed(() =>
  props.data.rows.filter((r: { hours: number }) => r.hours > 0)
);
</script>
