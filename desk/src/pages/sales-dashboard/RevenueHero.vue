<template>
  <!-- the top row: won revenue against the target, the top three by won value, and the
       period's money in four small cards -->
  <div class="grid grid-cols-1 gap-4 lg:grid-cols-12">
    <!-- won revenue against the month's target, as a half gauge -->
    <CcCard
      class="lg:col-span-3"
      accent="pink"
      :icon="LucideTarget"
      :title="target ? __('Won revenue vs target') : __('Won revenue')"
    >
      <template v-if="target" #actions>
        <span
          class="cc-pill rounded-md px-1.5 py-0.5 text-xs font-bold tabular-nums"
          >{{ targetPercent }}%</span
        >
      </template>
      <div class="relative mx-auto w-full max-w-[15rem]">
        <svg
          viewBox="0 0 180 100"
          class="w-full"
          role="img"
          :aria-label="
            target
              ? __(
                  '{0} won, {1}% of the {2} target',
                  fullAmount(wonValue, currency),
                  String(targetPercent),
                  fullAmount(target, currency)
                )
              : __('{0} won', fullAmount(wonValue, currency))
          "
        >
          <path
            d="M 14 92 A 76 76 0 0 1 166 92"
            fill="none"
            stroke="currentColor"
            class="text-surface-gray-3"
            stroke-width="14"
            stroke-linecap="round"
          />
          <path
            v-if="gaugePercent"
            d="M 14 92 A 76 76 0 0 1 166 92"
            fill="none"
            stroke="var(--accent)"
            class="cc-arc"
            stroke-width="14"
            stroke-linecap="round"
            pathLength="100"
            :stroke-dasharray="`${gaugePercent} 100`"
          />
        </svg>
        <div
          class="absolute inset-x-0 bottom-0 flex flex-col items-center"
          aria-hidden="true"
        >
          <span
            class="cc-ink cc-glow font-mono text-[22px] font-bold leading-none tabular-nums"
            :title="fullAmount(wonValue, currency)"
            >{{ shortAmount(wonValue, currency) }}</span
          >
          <span class="mt-1 text-[11px] text-ink-gray-6">{{
            target
              ? __("{0}% of target", String(targetPercent))
              : periodLabel.toLowerCase()
          }}</span>
        </div>
      </div>
      <p
        v-if="unpriced"
        class="cc-pill flex items-start gap-1.5 rounded-md px-2 py-1 text-[11px]"
        :style="accentStyle('amber')"
      >
        <LucideTriangleAlert class="mt-px size-3 shrink-0" aria-hidden="true" />
        {{
          unpriced === 1
            ? __("1 won lead has no amount, so it isn't counted here.")
            : __(
                "{0} won leads have no amount, so they aren't counted here.",
                String(unpriced)
              )
        }}
      </p>
      <dl class="flex justify-between gap-3 text-xs">
        <div class="flex flex-col">
          <dt class="text-ink-gray-6">
            {{ target ? __("Still to target") : __("Deals won") }}
          </dt>
          <dd class="font-mono font-semibold tabular-nums text-ink-gray-9">
            {{
              target
                ? shortAmount(Math.max(target - wonValue, 0), currency)
                : wonCount
            }}
          </dd>
        </div>
        <div class="flex flex-col items-end">
          <dt class="text-ink-gray-6">
            {{ target ? __("Target") : __("Before") }}
          </dt>
          <dd class="font-mono font-semibold tabular-nums text-ink-gray-9">
            {{
              target
                ? shortAmount(target, currency)
                : previous
                ? shortAmount(previous.value, currency)
                : "—"
            }}
          </dd>
        </div>
      </dl>
    </CcCard>

    <!-- the top three by won value: first in the middle, raised, with the crown -->
    <CcCard
      class="lg:col-span-6"
      accent="amber"
      :icon="LucideTrophy"
      :title="__('Top revenue by salesperson')"
    >
      <template #actions>
        <span class="cc-pill rounded-md px-2 py-0.5 text-xs font-semibold">{{
          __("Top 3 podium")
        }}</span>
      </template>
      <p
        v-if="!podium.length"
        class="flex flex-1 items-center justify-center py-8 text-sm text-ink-gray-6"
      >
        {{
          showsPodium
            ? __("No deals won yet in this period.")
            : __("Pick everyone to see the podium.")
        }}
      </p>
      <ol
        v-else
        class="grid flex-1 grid-cols-3 items-end gap-2 pt-2"
        :aria-label="__('Top revenue by salesperson')"
      >
        <li
          v-for="spot in spots"
          :key="spot.place"
          class="min-w-0"
          :style="{ order: spot.order }"
        >
          <button
            v-if="spot.entry"
            type="button"
            class="flex w-full min-w-0 flex-col items-center gap-1 rounded-xl px-1 py-2 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            :class="spot.place === 1 ? '' : 'mt-6'"
            :aria-label="
              __(
                'Place {0}: {1}, {2} won from {3} deals',
                String(spot.entry.rank),
                spot.entry.full_name,
                fullAmount(spot.entry.won_value, currency),
                String(spot.entry.won)
              )
            "
            @click="emit('open', spot.entry.user)"
          >
            <span
              class="flex flex-col items-center"
              :style="accentStyle(spot.accent)"
              aria-hidden="true"
            >
              <LucideCrown
                v-if="spot.place === 1"
                class="cc-ink mb-0.5 size-6 fill-current"
              />
              <span
                v-else
                class="cc-pill mb-1 rounded-md px-1.5 text-[11px] font-bold"
                >#{{ spot.entry.rank }}</span
              >
              <span class="relative">
                <PersonAvatar
                  :name="spot.entry.full_name"
                  size="xl"
                  class="ring-[3px] ring-[color:var(--accent)]"
                  :class="spot.place === 1 ? 'scale-110' : ''"
                />
                <span
                  v-if="spot.place === 1"
                  class="cc-fill absolute -bottom-1 -right-2 rounded-md px-1 text-[10px] font-bold text-white"
                  >#1</span
                >
              </span>
            </span>
            <span
              class="mt-2 w-full truncate text-center text-sm font-semibold text-ink-gray-9"
              aria-hidden="true"
              >{{ spot.entry.full_name }}</span
            >
            <span
              class="cc-ink font-mono text-base font-bold tabular-nums"
              :style="accentStyle('green')"
              aria-hidden="true"
              >{{ shortAmount(spot.entry.won_value, currency) }}</span
            >
            <span class="text-[11px] text-ink-gray-6" aria-hidden="true">{{
              spot.entry.won === 1
                ? __("1 deal won")
                : __("{0} deals won", String(spot.entry.won))
            }}</span>
          </button>
          <span
            v-else
            class="mx-auto block size-14 rounded-full border border-dashed border-outline-gray-3"
            aria-hidden="true"
          />
        </li>
      </ol>
    </CcCard>

    <!-- the period's money in four small cards -->
    <div class="grid grid-cols-2 content-start gap-4 lg:col-span-3">
      <div
        v-for="mini in minis"
        :key="mini.label"
        class="cc-card flex min-w-0 flex-col gap-1 p-3"
        :style="accentStyle(mini.accent)"
      >
        <span
          class="flex items-center gap-1 text-[10px] font-bold uppercase tracking-[0.06em] text-ink-gray-7"
        >
          <component
            :is="mini.icon"
            class="cc-ink size-3.5 shrink-0"
            aria-hidden="true"
          />
          <span class="truncate">{{ mini.label }}</span>
        </span>
        <span
          class="cc-ink cc-glow truncate font-mono text-lg font-bold tabular-nums"
          :title="mini.title"
          >{{ mini.value }}</span
        >
        <span
          v-if="mini.change"
          class="cc-ink inline-flex items-center gap-0.5 text-[11px] font-medium tabular-nums"
          :style="accentStyle(mini.change.up ? 'green' : 'red')"
        >
          <component
            :is="mini.change.up ? LucideArrowUp : LucideArrowDown"
            class="size-3 shrink-0"
            aria-hidden="true"
          />
          {{ mini.change.text }}
        </span>
        <span v-else-if="mini.sub" class="text-[11px] text-ink-gray-6">{{
          mini.sub
        }}</span>
      </div>
      <p v-if="moneyNote" class="col-span-2 text-xs text-ink-gray-6">
        {{ moneyNote }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import PersonAvatar from "@/components/PersonAvatar.vue";
import { fullAmount, shortAmount } from "@/pages/leads/business/businessFormat";
import { __ } from "@/translation";
import { computed, type Component } from "vue";
import LucideArrowDown from "~icons/lucide/arrow-down";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucideCalendar from "~icons/lucide/calendar";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCrown from "~icons/lucide/crown";
import LucideTarget from "~icons/lucide/target";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideTrophy from "~icons/lucide/trophy";
import LucideWallet from "~icons/lucide/wallet";
import CcCard from "./CcCard.vue";
import { accentStyle, percent, type Accent } from "./salesDashboard";

export interface PodiumPerson {
  user: string;
  full_name: string;
  won: number;
  won_value: number;
  /** 1, 2, 2, 4: people level share a place */
  rank: number;
}

const props = defineProps<{
  currency: string;
  /** "This month", "Today"… */
  periodLabel: string;
  wonValue: number;
  wonCount: number;
  /** won leads with no amount: counted in `wonCount`, not in `wonValue` */
  unpriced: number;
  /** the same days of the period before: won value and deals */
  previous: { value: number; won: number } | null;
  /** the month's won value target; null outside the month view or without targets */
  target: number | null;
  /** collected and still to collect; null when the ERP site didn't count it */
  money: { advances: number; to_collect: number } | null;
  /** why the money is missing, when it is */
  moneyNote: string;
  /** everyone ranked, first first */
  podium: PodiumPerson[];
  /** false with one person picked: there is no podium to show */
  showsPodium: boolean;
}>();
const emit = defineEmits<{ open: [user: string] }>();

const targetPercent = computed(() =>
  props.target ? percent(props.wonValue, props.target) : 0
);
const gaugePercent = computed(() =>
  props.target ? Math.min(targetPercent.value, 100) : 0
);

const SPOTS: { place: number; order: number; accent: Accent }[] = [
  { place: 1, order: 2, accent: "amber" },
  { place: 2, order: 1, accent: "blue" },
  { place: 3, order: 3, accent: "orange" },
];
const spots = computed(() =>
  SPOTS.map((spot) => ({
    ...spot,
    entry: props.podium[spot.place - 1] ?? null,
  }))
);

// against the same days before: the sign and the share, never colour alone
function changeOf(now: number, before: number | undefined, money: boolean) {
  if (before == null || now === before) return null;
  const up = now > before;
  const shown = money
    ? shortAmount(before, props.currency)
    : before.toLocaleString();
  const text = before
    ? __(
        "{0}{1}% vs {2}",
        up ? "+" : "",
        String(Math.round(((now - before) / before) * 100)),
        shown
      )
    : __("vs {0} before", shown);
  return { up, text };
}

const minis = computed(() => {
  const c = props.currency;
  const before = props.previous;
  const list: {
    label: string;
    value: string;
    title?: string;
    sub?: string;
    accent: Accent;
    icon: Component;
    change?: { up: boolean; text: string } | null;
  }[] = [
    {
      label: props.periodLabel,
      value: shortAmount(props.wonValue, c),
      title: fullAmount(props.wonValue, c),
      accent: "blue",
      icon: LucideCalendar,
      change: changeOf(props.wonValue, before?.value, true),
      sub: before ? __("same as before") : __("won"),
    },
    {
      label: __("Total won"),
      value: __("{0} deals", String(props.wonCount)),
      accent: "orange",
      icon: LucideTrophy,
      change: changeOf(props.wonCount, before?.won, false),
      sub: before ? __("same as before") : undefined,
    },
  ];
  if (props.money)
    list.push(
      {
        label: __("Collected"),
        value: shortAmount(props.money.advances, c),
        title: fullAmount(props.money.advances, c),
        accent: "cyan",
        icon: LucideCircleCheck,
        sub: __("received in the period"),
      },
      {
        label: __("To collect"),
        value: shortAmount(props.money.to_collect, c),
        title: fullAmount(props.money.to_collect, c),
        accent: "red",
        icon: LucideWallet,
        sub: __("outstanding now"),
      }
    );
  return list;
});
</script>
