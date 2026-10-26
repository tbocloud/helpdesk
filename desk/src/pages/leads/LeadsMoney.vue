<template>
  <!-- proposals sent, won and advances in the period; what is still to come in, now -->
  <section
    class="min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-labelledby="ids.heading"
    :aria-busy="loading"
  >
    <header
      class="flex flex-wrap items-baseline justify-between gap-2 border-b border-outline-gray-1 px-4 py-3"
    >
      <h2 :id="ids.heading" class="text-base-medium text-ink-gray-9">
        {{ __("Proposals & money") }}
      </h2>
      <span class="text-xs text-ink-gray-6">{{
        __("Sent, won and advances in this period · still to collect, now")
      }}</span>
    </header>

    <!-- shown once the ERP site answered; a failed first read says so here -->
    <div
      v-if="!m"
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
            "Couldn't load the proposals and payments: {0}",
            errorText(error, __("Check your connection."))
          )
        }}
      </p>
      <Button :label="__('Try again')" @click="emit('retry')" />
    </div>

    <template v-else>
      <div class="grid grid-cols-2 gap-3 p-4 lg:grid-cols-4">
        <StatTile
          compact
          :label="__('Proposals sent')"
          :value="amount(t.proposals_value)"
          :sub="
            t.proposals_sent === 1
              ? __('1 sent')
              : __('{0} sent', String(t.proposals_sent))
          "
          :icon="LucideFileText"
          :to="proposalsLink"
        />
        <StatTile
          compact
          :label="__('Won')"
          :value="amount(t.won_value)"
          :sub="t.won === 1 ? __('1 lead') : __('{0} leads', String(t.won))"
          :icon="LucideTrophy"
          :icon-tone="t.won ? 'success' : 'neutral'"
          :to="wonLink"
        />
        <StatTile
          compact
          :label="__('Advances received')"
          :value="amount(t.advances)"
          :icon="LucideWallet"
          :icon-tone="t.advances ? 'success' : 'neutral'"
        />
        <StatTile
          compact
          :label="__('Still to collect')"
          :value="amount(t.to_collect)"
          :sub="t.overdue ? __('{0} overdue', amount(t.overdue)) : undefined"
          :icon="t.overdue ? LucideCalendarX : LucideHourglass"
          :icon-tone="t.overdue ? 'danger' : 'neutral'"
        />
      </div>
      <p
        v-if="t.unpriced_sent"
        class="-mt-1 flex items-start gap-2 px-4 pb-3 text-p-xs text-ink-gray-6"
      >
        <LucideInfo
          class="mt-0.5 size-3.5 shrink-0 text-ink-gray-5"
          aria-hidden="true"
        />
        {{
          t.unpriced_sent === 1
            ? __("1 proposal went out without a price; it isn't counted above.")
            : __(
                "{0} proposals went out without a price; they aren't counted above.",
                String(t.unpriced_sent)
              )
        }}
      </p>

      <div
        class="grid border-t border-outline-gray-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:divide-x lg:divide-outline-gray-1"
      >
        <!-- expected money by month, from the splits' due dates -->
        <div class="flex min-w-0 flex-col">
          <h3
            :id="ids.months"
            class="px-4 pb-1 pt-3 text-sm-medium text-ink-gray-8"
          >
            {{ __("Expected by month") }}
          </h3>
          <p v-if="!months.length" class="px-4 py-3 text-p-sm text-ink-gray-6">
            {{ __("Nothing left to collect.") }}
          </p>
          <ul
            v-else
            role="list"
            class="flex flex-col pb-3"
            :aria-labelledby="ids.months"
          >
            <li
              v-for="row in months"
              :key="row.key"
              class="grid grid-cols-[minmax(0,7rem)_minmax(0,1fr)_auto] items-center gap-3 px-4 py-1.5"
            >
              <span
                class="flex min-w-0 items-center gap-1 text-sm"
                :class="row.overdue ? 'text-danger' : 'text-ink-gray-8'"
              >
                <LucideCalendarX
                  v-if="row.overdue"
                  class="size-3.5 shrink-0"
                  aria-hidden="true"
                />
                <span class="truncate">{{ row.label }}</span>
              </span>
              <span
                class="block h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                aria-hidden="true"
              >
                <span
                  class="block h-full rounded-full"
                  :class="row.overdue ? 'bg-danger' : 'bg-surface-gray-7'"
                  :style="{ width: `${share(row.amount)}%` }"
                />
              </span>
              <span
                class="text-right font-mono text-sm tabular-nums text-ink-gray-9"
                >{{ amount(row.amount) }}</span
              >
            </li>
          </ul>
        </div>

        <!-- every split still being collected, by due date -->
        <div
          class="flex min-w-0 flex-col border-t border-outline-gray-1 lg:border-t-0"
        >
          <div
            class="flex flex-wrap items-center justify-between gap-2 px-4 pb-1 pt-3"
          >
            <h3 :id="ids.splits" class="text-sm-medium text-ink-gray-8">
              {{ __("Payment splits") }}
            </h3>
            <Button
              v-if="splits.length > 1"
              variant="ghost"
              size="sm"
              :label="
                newestFirst
                  ? __('Due date: latest first')
                  : __('Due date: soonest first')
              "
              :aria-label="
                newestFirst
                  ? __('Sorted by due date, latest first. Sort soonest first')
                  : __('Sorted by due date, soonest first. Sort latest first')
              "
              @click="newestFirst = !newestFirst"
            >
              <template #suffix>
                <component
                  :is="newestFirst ? LucideArrowUp : LucideArrowDown"
                  class="size-3.5"
                  aria-hidden="true"
                />
              </template>
            </Button>
          </div>
          <p v-if="!splits.length" class="px-4 py-3 text-p-sm text-ink-gray-6">
            {{
              __(
                "No proposal or order is waiting on a payment. Splits show here once a proposal goes out."
              )
            }}
          </p>
          <template v-else>
            <!-- column heads, on wide screens; each row reads on its own on a phone -->
            <div
              class="hidden grid-cols-[minmax(0,1.6fr)_minmax(0,1.4fr)_6rem_6.5rem_7.5rem] gap-3 px-4 py-1.5 text-xs text-ink-gray-6 md:grid"
              aria-hidden="true"
            >
              <span>{{ __("Client") }}</span>
              <span>{{ __("Split") }}</span>
              <span>{{ __("Due") }}</span>
              <span>{{ __("Status") }}</span>
              <span class="text-right">{{ __("Amount") }}</span>
            </div>
            <ul role="list" :aria-labelledby="ids.splits">
              <li
                v-for="row in shown"
                :key="`${row.document}-${row.idx}`"
                class="border-t border-outline-gray-1"
              >
                <router-link
                  :to="{ name: 'Lead', params: { leadId: row.lead } }"
                  class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 px-4 py-2 transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1.4fr)_6rem_6.5rem_7.5rem]"
                >
                  <span class="flex min-w-0 flex-col">
                    <span class="truncate text-sm text-ink-gray-9">{{
                      row.company_name || row.lead_name || row.lead
                    }}</span>
                    <span
                      v-if="!ownerPicked && row.owner_name"
                      class="truncate text-xs text-ink-gray-6"
                      >{{ row.owner_name }}</span
                    >
                  </span>
                  <span
                    class="order-last col-span-2 flex min-w-0 flex-col md:order-none md:col-span-1"
                  >
                    <span class="truncate text-sm text-ink-gray-8">
                      {{ row.label || __("Full amount") }}
                      <span
                        v-if="row.percent && row.percent !== 100"
                        class="font-mono text-xs tabular-nums text-ink-gray-6"
                        >{{ row.percent }}%</span
                      >
                    </span>
                    <span class="truncate text-xs text-ink-gray-6">{{
                      documentText(row)
                    }}</span>
                  </span>
                  <span
                    class="hidden font-mono text-sm tabular-nums md:block"
                    :class="
                      row.due_date ? 'text-ink-gray-8' : 'text-ink-gray-6'
                    "
                    >{{ dueText(row) }}</span
                  >
                  <span class="hidden md:block">
                    <TaskyBadge
                      :label="STATUS[row.status].label"
                      :tone="STATUS[row.status].tone"
                      :icon="STATUS[row.status].icon"
                    />
                  </span>
                  <span class="flex flex-col items-end">
                    <span
                      class="font-mono text-sm tabular-nums text-ink-gray-9"
                      >{{
                        amount(
                          row.status === "Received"
                            ? row.amount
                            : row.outstanding
                        )
                      }}</span
                    >
                    <span
                      v-if="row.received && row.outstanding"
                      class="font-mono text-xs tabular-nums text-ink-gray-6"
                      >{{ __("of {0}", amount(row.amount)) }}</span
                    >
                    <!-- the due date and status, under the amount on a phone -->
                    <span class="mt-0.5 flex items-center gap-1.5 md:hidden">
                      <span
                        class="font-mono text-xs tabular-nums text-ink-gray-6"
                        >{{ dueText(row) }}</span
                      >
                      <TaskyBadge
                        :label="STATUS[row.status].label"
                        :tone="STATUS[row.status].tone"
                        :icon="STATUS[row.status].icon"
                      />
                    </span>
                  </span>
                </router-link>
              </li>
            </ul>
            <div
              v-if="
                splits.length > LIMIT || (m.splits_total ?? 0) > splits.length
              "
              class="flex flex-wrap items-center justify-between gap-2 border-t border-outline-gray-1 px-4 py-2"
            >
              <span class="font-mono text-xs tabular-nums text-ink-gray-6">{{
                __(
                  "{0} of {1}",
                  String(shown.length),
                  String(m.splits_total ?? splits.length)
                )
              }}</span>
              <Button
                v-if="splits.length > LIMIT"
                variant="ghost"
                size="sm"
                :label="showAll ? __('Show fewer') : __('Show all')"
                @click="showAll = !showAll"
              />
            </div>
          </template>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { money as formatMoney } from "@/components/invoicing/invoices";
import StatTile from "@/components/StatTile.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, dayjs } from "frappe-ui";
import { computed, ref, useId, type Component } from "vue";
import type { RouteLocationRaw } from "vue-router";
import LucideArrowDown from "~icons/lucide/arrow-down";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCalendarX from "~icons/lucide/calendar-x";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideFileText from "~icons/lucide/file-text";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideInfo from "~icons/lucide/info";
import LucideTrophy from "~icons/lucide/trophy";
import LucideWallet from "~icons/lucide/wallet";
import type { MoneySplit, ProposalMoney, SplitStatus } from "./leads";

const props = defineProps<{
  money?: ProposalMoney;
  error?: unknown;
  loading?: boolean;
  /** one person's figures (theirs, or the owner picked): no owner under each client */
  ownerPicked?: boolean;
  proposalsLink: RouteLocationRaw;
  wonLink: RouteLocationRaw;
}>();
const emit = defineEmits<{ retry: [] }>();

const LIMIT = 8;
// colour only where the status means something, always with its word and an icon
const STATUS: Record<
  SplitStatus,
  { label: string; tone: Tone; icon?: Component }
> = {
  Received: {
    label: __("Received"),
    tone: "success",
    icon: LucideCircleCheck,
  },
  Overdue: { label: __("Overdue"), tone: "danger", icon: LucideCalendarX },
  Due: { label: __("Due"), tone: "info", icon: LucideCalendarClock },
  Upcoming: { label: __("Upcoming"), tone: "neutral" },
};

const ids = { heading: useId(), months: useId(), splits: useId() };
const newestFirst = ref(false);
const showAll = ref(false);

const m = computed(() => (props.money?.available ? props.money : undefined));
const t = computed(() => m.value!.totals!);

function amount(value: number) {
  const currency = m.value?.currency;
  return currency ? formatMoney(value, currency, true) : String(value);
}

// overdue first, then each month with money due, later, and on a milestone
const months = computed(() => {
  const b = m.value?.by_month;
  if (!b) return [];
  const rows = [
    { key: "overdue", label: __("Overdue"), amount: b.overdue, overdue: true },
    ...b.months.map((row) => ({
      key: row.month,
      label: dayjs(row.month).format("MMM YYYY"),
      amount: row.amount,
      overdue: false,
    })),
    { key: "later", label: __("Later"), amount: b.later, overdue: false },
    {
      key: "undated",
      label: __("On milestone"),
      amount: b.undated,
      overdue: false,
    },
  ];
  return rows.filter((row) => row.amount > 0);
});
const monthMax = computed(() =>
  Math.max(...months.value.map((row) => row.amount), 1)
);

function share(value: number) {
  return Math.round((value / monthMax.value) * 100);
}

// the ERP site sends them soonest first, undated last
const splits = computed(() => {
  const rows = m.value?.splits ?? [];
  if (!newestFirst.value) return rows;
  const dated = rows.filter((row) => row.due_date).reverse();
  return [...dated, ...rows.filter((row) => !row.due_date)];
});
const shown = computed(() =>
  showAll.value ? splits.value : splits.value.slice(0, LIMIT)
);

function dueText(row: MoneySplit) {
  return row.due_date
    ? dayjs(row.due_date).format("D MMM YYYY")
    : __("On milestone");
}

function documentText(row: MoneySplit) {
  return row.document_type === "Sales Order"
    ? __("Sales order {0}", row.document)
    : [__("Quotation {0}", row.document), row.quote_status]
        .filter(Boolean)
        .join(" · ");
}
</script>
