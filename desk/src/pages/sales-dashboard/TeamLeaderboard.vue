<template>
  <!-- the team ranked by what they won, with the work behind it, person by person -->
  <section
    class="cc-card min-w-0 overflow-hidden"
    :style="accentStyle('amber')"
    :aria-labelledby="headingId"
  >
    <header
      class="flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--cc-card-border)] px-4 py-4"
    >
      <div class="flex flex-col gap-0.5">
        <h2
          :id="headingId"
          class="flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.06em] text-ink-gray-9"
        >
          <LucideTrophy class="cc-ink size-4" aria-hidden="true" />
          {{ title }}
        </h2>
        <p class="text-xs text-ink-gray-6">
          {{
            monthName
              ? __(
                  "Ranked by won value, with calls, meetings and {0} target progress",
                  monthName
                )
              : __("Ranked by won value, with the calls and meetings behind it")
          }}
        </p>
      </div>
      <div v-if="monthName" class="flex gap-1.5">
        <span
          class="cc-pill inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold"
          :style="accentStyle('blue')"
        >
          <LucideCircleCheck class="size-3" aria-hidden="true" />
          {{ __("{0} on track", String(standing.onTrack)) }}
        </span>
        <span
          v-if="standing.behind"
          class="cc-pill inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold"
          :style="accentStyle('red')"
        >
          <LucideTrendingDown class="size-3" aria-hidden="true" />
          {{ __("{0} behind", String(standing.behind)) }}
        </span>
      </div>
    </header>
    <PartError :message="error" class="m-4" />
    <p
      v-if="rows && !rows.length"
      class="px-4 py-10 text-center text-sm text-ink-gray-6"
    >
      {{
        __(
          "No salespeople to show. Pick them in Settings → Agents → Department wall → Sales team."
        )
      }}
    </p>
    <div v-else-if="rows" class="overflow-x-auto">
      <table class="cc-cols w-full min-w-[68rem] text-sm">
        <thead>
          <tr
            class="h-11 text-left text-[11px] font-bold uppercase tracking-[0.06em] text-ink-gray-7"
          >
            <th scope="col" class="w-12 pl-4 pr-2">{{ __("Rank") }}</th>
            <th scope="col" class="px-3">{{ __("Person") }}</th>
            <th scope="col" class="px-3">{{ callsLabel }}</th>
            <th scope="col" class="px-3">
              <abbr
                :title="
                  __(
                    'Leads on their call lists where someone answered, and the share of those called'
                  )
                "
                >{{ __("Answered") }}</abbr
              >
            </th>
            <th scope="col" class="px-3">
              <abbr :title="__('Talk time per answered call')">{{
                __("Avg talk")
              }}</abbr>
            </th>
            <th scope="col" class="px-3 text-right">{{ __("Meetings") }}</th>
            <th scope="col" class="px-3 text-right">{{ __("Proposals") }}</th>
            <th scope="col" class="px-3 text-right">{{ __("Won") }}</th>
            <th scope="col" class="px-3 text-right">{{ __("Won value") }}</th>
            <th v-if="monthName" scope="col" class="px-3">
              {{ __("Target progress") }}
            </th>
            <th scope="col" class="pl-3 pr-4">
              <span class="sr-only">{{ __("Leads") }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.user"
            class="h-16 border-t border-[color:var(--cc-card-border)] hover:bg-surface-gray-1"
          >
            <td class="pl-4 pr-2">
              <span
                class="grid size-7 place-items-center rounded-full bg-surface-gray-2 text-xs font-semibold tabular-nums text-ink-gray-8"
                >{{ row.rank }}</span
              >
            </td>
            <th scope="row" class="px-3 text-left font-normal">
              <span class="flex items-center gap-2.5">
                <PersonAvatar :name="row.full_name" size="lg" />
                <span class="font-semibold text-ink-gray-9">{{
                  row.full_name
                }}</span>
              </span>
            </th>
            <td class="px-3">
              <span class="tabular-nums text-ink-gray-9">
                <b>{{ row.called }}</b>
                <span v-if="row.given" class="text-ink-gray-6">
                  / {{ row.given }}</span
                >
              </span>
              <span
                v-if="row.given"
                class="mt-1.5 block h-1.5 w-28 overflow-hidden rounded-full bg-surface-gray-2"
                role="meter"
                :aria-valuenow="percent(row.called, row.given)"
                aria-valuemin="0"
                aria-valuemax="100"
                :aria-label="__('Share of handed-out calls made')"
              >
                <span
                  class="cc-fill block h-full rounded-full"
                  :style="{
                    ...accentStyle('blue'),
                    width: `${Math.min(percent(row.called, row.given), 100)}%`,
                  }"
                />
              </span>
            </td>
            <td class="px-3 tabular-nums">
              <span class="flex items-center gap-2">
                <span
                  class="cc-ink inline-flex items-center gap-1 font-bold"
                  :style="accentStyle('green')"
                >
                  <LucideCircleCheck class="size-3.5" aria-hidden="true" />
                  {{ row.contacted }}
                </span>
                <span
                  class="cc-pill rounded-md px-1.5 py-0.5 text-[11px] font-semibold"
                  :style="accentStyle(rateAccent(row))"
                  >{{ percent(row.contacted, row.called) }}%</span
                >
              </span>
            </td>
            <td class="px-3">
              <span
                v-if="row.talkPerCall != null"
                class="cc-pill inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[11px] tabular-nums"
                :style="accentStyle('blue')"
              >
                <LucideClock class="size-3" aria-hidden="true" />
                {{ formatElapsed(row.talkPerCall) }}
              </span>
              <span v-else class="text-ink-gray-5">—</span>
            </td>
            <td class="px-3 text-right tabular-nums text-ink-gray-8">
              {{ row.meetings ?? "—" }}
            </td>
            <td class="px-3 text-right tabular-nums text-ink-gray-8">
              {{ row.proposals ?? "—" }}
            </td>
            <td
              class="cc-ink px-3 text-right font-mono font-bold tabular-nums"
              :style="accentStyle('green')"
            >
              {{ row.won ?? "—" }}
            </td>
            <td
              class="cc-ink px-3 text-right font-mono font-bold tabular-nums"
              :style="accentStyle('green')"
              :title="
                row.wonValue == null
                  ? undefined
                  : fullAmount(row.wonValue, currency)
              "
            >
              {{
                row.wonValue == null ? "—" : shortAmount(row.wonValue, currency)
              }}
            </td>
            <td v-if="monthName" class="px-3">
              <span
                v-if="row.target?.percent != null"
                class="flex items-center gap-2"
              >
                <TargetRing
                  class="!size-10 [&_svg]:!size-10"
                  :actual="row.target.percent"
                  :target="100"
                  :tone="row.target.behind ? 'danger' : 'success'"
                  :status-text="
                    row.target.behind ? __('behind') : __('on track')
                  "
                  :text="`${row.target.percent}%`"
                />
                <span
                  class="cc-pill inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.06em]"
                  :style="accentStyle(row.target.behind ? 'red' : 'blue')"
                >
                  {{ row.target.behind ? __("Behind") : __("On track") }}
                </span>
              </span>
              <span v-else class="text-xs text-ink-gray-5">
                {{ __("No targets") }}
              </span>
            </td>
            <td class="pl-3 pr-4 text-right">
              <CardLink
                :to="{
                  name: 'Leads',
                  query: { view: 'all', ...leadsQuery, owner: row.user },
                }"
              >
                {{ __("Leads") }}
              </CardLink>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import PersonAvatar from "@/components/PersonAvatar.vue";
import { fullAmount, shortAmount } from "@/pages/leads/business/businessFormat";
import TargetRing from "@/pages/leads/TargetRing.vue";
import { formatElapsed } from "@/pages/tasky/taskMeta";
import { __ } from "@/translation";
import { computed, useId } from "vue";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideTrendingDown from "~icons/lucide/trending-down";
import LucideTrophy from "~icons/lucide/trophy";
import CardLink from "./CardLink.vue";
import PartError from "./PartError.vue";
import { accentStyle, percent, type Accent } from "./salesDashboard";

/** One salesperson on the leaderboard; null: the ERP site didn't count that figure. */
export interface LeaderRow {
  user: string;
  full_name: string;
  rank: number;
  given: number;
  called: number;
  contacted: number;
  /** seconds of talk per answered call; null when the call log has no talk time */
  talkPerCall: number | null;
  meetings: number | null;
  proposals: number | null;
  won: number | null;
  wonValue: number | null;
  /** the month's targets, as the Sales targets page counts them */
  target?: { percent: number | null; behind: number };
}

const props = defineProps<{
  title: string;
  /** "Calls today" */
  callsLabel: string;
  rows: LeaderRow[] | null;
  error?: string;
  currency: string;
  /** the targets' month in words; empty: no target column */
  monthName: string;
  /** the department and source the Leads list opens with */
  leadsQuery: Record<string, string | undefined>;
}>();

const headingId = useId();

const standing = computed(() => {
  const counted = (props.rows ?? []).filter((r) => r.target?.percent != null);
  const behind = counted.filter((r) => r.target!.behind).length;
  return { behind, onTrack: counted.length - behind };
});

// the contact rate read at a glance: half or more answered is good, under a third is low
function rateAccent(row: LeaderRow): Accent {
  const rate = percent(row.contacted, row.called);
  if (!row.called) return "blue";
  return rate >= 50 ? "green" : rate >= 30 ? "amber" : "red";
}
</script>
