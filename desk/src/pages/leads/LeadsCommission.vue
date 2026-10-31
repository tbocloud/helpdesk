<template>
  <div class="flex flex-col gap-5">
    <div
      class="flex flex-wrap items-end gap-3"
      role="group"
      :aria-label="__('Month')"
    >
      <FormControl
        v-model="month"
        type="select"
        class="w-full sm:w-56"
        :label="__('Month')"
        :options="monthOptions"
      />
      <div v-if="data?.can_manage" class="ml-auto flex flex-wrap gap-2">
        <Button
          variant="solid"
          :label="__('Generate drafts')"
          :loading="generating"
          @click="generate"
        >
          <template #prefix>
            <LucideFilePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
    </div>

    <TaskyState
      v-if="page.error && !data"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the commission')"
      :message="
        errorText(page.error, __('Check your connection and try again.'))
      "
    >
      <Button :label="__('Try again')" @click="reload" />
    </TaskyState>

    <TaskyState
      v-else-if="page.data && !page.data.available"
      :icon="LucideCloudOff"
      :title="__('Commission isn\'t available yet')"
      :message="__('The ERP site needs the latest TBO Smart.')"
    />

    <div
      v-else-if="!data"
      class="flex flex-col gap-3"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div
          v-for="i in 4"
          :key="i"
          class="h-[72px] animate-pulse rounded-xl bg-surface-gray-2"
        />
      </div>
      <div class="h-56 animate-pulse rounded-xl bg-surface-gray-2" />
    </div>

    <template v-else>
      <div
        v-if="page.error"
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
              "Couldn't update the commission: {0} These numbers may be out of date.",
              errorText(page.error, __("Check your connection."))
            )
          }}
        </p>
        <Button :label="__('Try again')" @click="reload" />
      </div>

      <p class="text-p-sm text-ink-gray-6">
        {{ scopeText }}
        <span v-if="page.loading" class="sr-only" aria-live="polite">{{
          __("Updating")
        }}</span>
      </p>

      <section
        class="grid grid-cols-2 gap-3 md:grid-cols-4"
        :aria-label="__('Totals')"
      >
        <StatTile
          compact
          :label="mine ? __('My collected') : __('Collected')"
          :value="fullAmount(data.totals.collected, data.currency)"
        />
        <StatTile
          compact
          :label="mine ? __('My commission') : __('Commission')"
          :value="fullAmount(data.totals.commission, data.currency)"
        />
        <StatTile
          v-if="mine && data.rows[0]"
          compact
          :label="__('Target reached')"
          :value="
            data.rows[0].target > 0 ? `${data.rows[0].achievement}%` : '–'
          "
          :sub="reachedText(data.rows[0])"
        />
        <StatTile
          v-else
          compact
          :label="__('People')"
          :value="String(data.rows.length)"
        />
        <StatTile
          v-if="data.unattributed"
          compact
          :label="__('Unattributed')"
          :value="fullAmount(data.unattributed.amount, data.currency)"
          :sub="__('{0} payments', String(data.unattributed.count))"
        />
      </section>

      <TaskyState
        v-if="!data.rows.length"
        :icon="LucideCoins"
        :title="
          mine
            ? __('Nothing collected for you in {0}', monthTitle(month))
            : __('No commission in {0}', monthTitle(month))
        "
        :message="emptyMessage"
      />

      <ul v-else role="list" class="flex flex-col gap-3">
        <li
          v-for="person in data.rows"
          :key="person.user"
          class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
        >
          <div class="flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3">
            <button
              type="button"
              class="flex min-w-0 flex-1 basis-56 flex-col gap-0.5 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              :aria-expanded="isOpen(person)"
              :aria-controls="`${uid}-${person.user}`"
              @click="toggle(person)"
            >
              <span class="flex items-center gap-1.5">
                <component
                  :is="isOpen(person) ? LucideChevronDown : LucideChevronRight"
                  class="size-4 shrink-0 text-ink-gray-5"
                  aria-hidden="true"
                />
                <span class="truncate text-base-medium text-ink-gray-9">{{
                  person.full_name
                }}</span>
              </span>
              <span class="ps-[22px] text-p-xs text-ink-gray-6">
                {{
                  person.plans.length
                    ? person.plans.join(", ")
                    : __("No plan matches")
                }}
                · {{ reachedText(person) }}
              </span>
            </button>

            <div class="flex w-40 flex-col gap-1">
              <span class="font-mono text-sm tabular-nums text-ink-gray-9">{{
                fullAmount(person.collected, data.currency)
              }}</span>
              <template v-if="person.target > 0">
                <div
                  class="h-1.5 overflow-hidden rounded-full bg-surface-gray-3"
                  role="progressbar"
                  :aria-valuenow="Math.min(person.achievement, 100)"
                  aria-valuemin="0"
                  aria-valuemax="100"
                  :aria-label="__('Target reached')"
                >
                  <div
                    class="h-full rounded-full"
                    :class="
                      person.achievement >= 100
                        ? 'bg-success'
                        : 'bg-surface-gray-6'
                    "
                    :style="{
                      width: `${Math.max(
                        Math.min(person.achievement, 100),
                        0
                      )}%`,
                    }"
                  />
                </div>
                <span class="font-mono text-xs tabular-nums text-ink-gray-6">
                  {{
                    __(
                      "{0}% of {1}",
                      String(person.achievement),
                      fullAmount(person.target, data.currency)
                    )
                  }}
                </span>
              </template>
              <span v-else class="text-xs text-ink-gray-5">{{
                __("No target")
              }}</span>
            </div>

            <div class="flex w-28 flex-col items-end gap-1">
              <span
                class="font-mono text-base-medium tabular-nums text-ink-gray-9"
                >{{ fullAmount(person.commission, data.currency) }}</span
              >
              <span
                v-if="person.status"
                class="inline-flex items-center gap-1 text-xs"
                :class="STATUS_INK[person.status]"
              >
                <component
                  :is="STATUS_ICON[person.status]"
                  class="size-3.5"
                  aria-hidden="true"
                />
                {{ STATUS_LABELS[person.status] }}
              </span>
              <span v-else class="text-xs text-ink-gray-5">{{
                __("Not drafted")
              }}</span>
            </div>

            <div v-if="data.can_manage" class="flex w-28 justify-end">
              <Button
                v-if="person.status === 'Draft'"
                variant="solid"
                :label="__('Approve')"
                :loading="busy === person.statement"
                @click="approve(person)"
              />
              <Button
                v-else-if="person.status === 'Approved'"
                :label="__('Mark paid')"
                :loading="busy === person.statement"
                @click="markPaid(person)"
              />
            </div>
          </div>

          <div
            v-if="isOpen(person)"
            :id="`${uid}-${person.user}`"
            class="flex flex-col gap-4 border-t border-outline-gray-1 bg-surface-gray-1 px-4 py-4"
          >
            <p v-if="person.frozen" class="text-p-xs text-ink-gray-6">
              {{
                __(
                  "Approved by {0}. These figures are as approved; later cancellations count in the month they happen.",
                  person.approved_by || ""
                )
              }}
            </p>

            <section :aria-label="__('Projects')">
              <h3 class="mb-1.5 text-sm text-ink-gray-7">
                {{ __("Projects") }}
              </h3>
              <div class="overflow-x-auto">
                <table class="w-full min-w-[32rem] text-sm">
                  <thead class="text-left text-xs text-ink-gray-6">
                    <tr>
                      <th class="py-1 pe-3 font-normal">{{ __("Project") }}</th>
                      <th class="py-1 pe-3 text-right font-normal">
                        {{ __("Collected") }}
                      </th>
                      <th class="py-1 pe-3 text-right font-normal">
                        {{ __("Share") }}
                      </th>
                      <th class="py-1 text-right font-normal">
                        {{ __("Commission") }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="row in person.projects"
                      :key="row.project + (row.plan || '')"
                      class="border-t border-outline-gray-1"
                    >
                      <td class="py-1.5 pe-3 text-ink-gray-8">
                        <span class="font-mono">{{
                          row.project || __("No project")
                        }}</span>
                        <span class="block text-xs text-ink-gray-6">{{
                          row.plan || __("No plan")
                        }}</span>
                      </td>
                      <td class="num">
                        {{ fullAmount(row.collected, data.currency) }}
                      </td>
                      <td class="num">{{ row.share_percent }}%</td>
                      <td class="num text-ink-gray-9">
                        {{ fullAmount(row.commission, data.currency) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <section v-if="person.breakdown.length" :aria-label="__('Slabs')">
              <h3 class="mb-1.5 text-sm text-ink-gray-7">
                {{ __("Slab breakdown") }}
              </h3>
              <div class="overflow-x-auto">
                <table class="w-full min-w-[32rem] text-sm">
                  <thead class="text-left text-xs text-ink-gray-6">
                    <tr>
                      <th class="py-1 pe-3 font-normal">{{ __("Slab") }}</th>
                      <th class="py-1 pe-3 text-right font-normal">
                        {{ __("Amount") }}
                      </th>
                      <th class="py-1 pe-3 text-right font-normal">
                        {{ __("Rate") }}
                      </th>
                      <th class="py-1 text-right font-normal">
                        {{ __("Commission") }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(row, i) in person.breakdown"
                      :key="i"
                      class="border-t border-outline-gray-1"
                    >
                      <td class="py-1.5 pe-3 text-ink-gray-8">
                        <span class="font-mono tabular-nums"
                          >{{ shortAmount(row.from_amount, data.currency) }} –
                          {{ shortAmount(row.to_amount, data.currency) }}</span
                        >
                        <span class="block text-xs text-ink-gray-6">
                          {{
                            row.above_target
                              ? __("Above target")
                              : row.slab_no
                              ? __("Slab {0}", String(row.slab_no))
                              : __("No slab")
                          }}
                          <template v-if="row.project">
                            · {{ row.project }}
                          </template>
                        </span>
                      </td>
                      <td class="num">
                        {{ fullAmount(row.amount, data.currency) }}
                      </td>
                      <td class="num">{{ row.rate }}%</td>
                      <td class="num text-ink-gray-9">
                        {{ fullAmount(row.commission, data.currency) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <section :aria-label="__('Payments')">
              <h3 class="mb-1.5 text-sm text-ink-gray-7">
                {{ __("Payments") }}
              </h3>
              <CommissionPayments
                :payments="person.payments"
                :currency="data.currency"
              />
            </section>
          </div>
        </li>
      </ul>

      <section
        v-if="data.unattributed"
        class="rounded-xl border border-outline-gray-2 bg-surface-base"
        :aria-labelledby="`${uid}-unattributed`"
      >
        <header
          class="flex flex-wrap items-baseline justify-between gap-2 px-4 py-3"
        >
          <h2
            :id="`${uid}-unattributed`"
            class="text-base-medium text-ink-gray-9"
          >
            {{ __("Unattributed") }}
          </h2>
          <span class="font-mono text-sm tabular-nums text-ink-gray-9">{{
            fullAmount(data.unattributed.amount, data.currency)
          }}</span>
        </header>
        <div
          class="flex flex-col gap-3 border-t border-outline-gray-1 px-4 py-3"
        >
          <p class="max-w-prose text-p-sm text-ink-gray-6">
            {{
              __(
                "Money received this month that earns no one commission, because it can't be followed to a project and a person: an advance not matched to an order or invoice, an order with no project, or a lead with no owner. Set the project on the order or invoice, or give the project a commission set-up, and it is counted when the drafts are generated again."
              )
            }}
          </p>
          <ul
            v-if="Object.keys(data.unattributed.reasons).length"
            role="list"
            class="flex flex-col gap-1"
          >
            <li
              v-for="(amount, reason) in data.unattributed.reasons"
              :key="reason"
              class="flex justify-between gap-3 text-sm text-ink-gray-8"
            >
              <span>{{ REASON_LABELS[reason] || reason }}</span>
              <span class="font-mono tabular-nums">{{
                fullAmount(amount, data.currency)
              }}</span>
            </li>
          </ul>
          <details v-if="data.unattributed.payments.length">
            <summary
              class="cursor-pointer rounded text-sm text-ink-gray-7 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            >
              {{ __("Show the payments") }}
            </summary>
            <div class="mt-2">
              <CommissionPayments
                :payments="data.unattributed.payments"
                :currency="data.currency"
              />
            </div>
          </details>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, createResource, FormControl, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCloudOff from "~icons/lucide/cloud-off";
import LucideCoins from "~icons/lucide/coins";
import LucideFilePen from "~icons/lucide/file-pen";
import LucideFilePlus from "~icons/lucide/file-plus";
import LucideWallet from "~icons/lucide/wallet";
import { fullAmount, shortAmount } from "./business/businessFormat";
import CommissionPayments from "./CommissionPayments.vue";
import {
  monthTitle,
  monthValue,
  reachedText,
  REASON_LABELS,
  STATUS_LABELS,
  type CommissionMonth,
  type CommissionPerson,
  type CommissionStatus,
} from "./commission";

const uid = useId();
const MONTHS_BACK = 12;
const monthOptions = Array.from({ length: MONTHS_BACK + 1 }, (_v, i) => {
  const value = monthValue(-i);
  return { label: monthTitle(value), value };
});
const month = ref(monthValue());
const opened = ref<Record<string, boolean>>({});
const generating = ref(false);
const busy = ref("");

const STATUS_ICON: Record<CommissionStatus, unknown> = {
  Draft: LucideFilePen,
  Approved: LucideCircleCheck,
  Paid: LucideWallet,
};
const STATUS_INK: Record<CommissionStatus, string> = {
  Draft: "text-ink-gray-6",
  Approved: "text-info",
  Paid: "text-success",
};

const page = createResource({
  url: "helpdesk.api.commission.get_commission",
  makeParams: () => ({ month: month.value }),
  auto: true,
});
const data = computed(() =>
  page.data?.available ? (page.data as CommissionMonth) : undefined
);
const mine = computed(() => data.value?.scope === "own");

watch(month, () => {
  opened.value = {};
  page.submit({ month: month.value });
});

const scopeText = computed(() => {
  const d = data.value;
  if (!d) return "";
  const title = monthTitle(month.value);
  if (d.scope === "own") return __("Your commission for {0}.", title);
  if (d.scope === "department")
    return __("Your department's commission for {0}.", title);
  return __("Everyone's commission for {0}.", title);
});

const emptyMessage = computed(() =>
  mine.value
    ? __(
        "Commission is worked out on money collected on projects you own. When a payment lands on one of yours it shows here."
      )
    : __(
        "No customer payment this month could be followed to a person. Check Unattributed below, and the commission plans in Settings."
      )
);

// a single person's own month opens by itself
function isOpen(person: CommissionPerson) {
  return (
    opened.value[person.user] ?? (mine.value && data.value?.rows.length === 1)
  );
}
function toggle(person: CommissionPerson) {
  opened.value = { ...opened.value, [person.user]: !isOpen(person) };
}

function reload() {
  page.reload();
}

function generate() {
  generating.value = true;
  call("helpdesk.api.commission.generate_statements", { month: month.value })
    .then((rows: { skipped: number }[]) => {
      const kept = rows.filter((r) => r.skipped).length;
      toast.success(
        kept
          ? __(
              "Drafts updated. {0} approved statements were left as they are.",
              String(kept)
            )
          : __("Drafts updated")
      );
      reload();
    })
    .catch((e: unknown) =>
      toast.error(errorText(e, __("Couldn't generate the drafts.")))
    )
    .finally(() => (generating.value = false));
}

function act(person: CommissionPerson, method: string, done: string) {
  if (!person.statement) return;
  busy.value = person.statement;
  call(`helpdesk.api.commission.${method}`, { name: person.statement })
    .then(() => {
      toast.success(done);
      reload();
    })
    .catch((e: unknown) => toast.error(errorText(e, __("That didn't work."))))
    .finally(() => (busy.value = ""));
}
const approve = (person: CommissionPerson) =>
  act(person, "approve_statement", __("Statement approved"));
const markPaid = (person: CommissionPerson) =>
  act(person, "mark_paid", __("Marked as paid"));

defineExpose({ reload });
</script>

<style scoped>
.num {
  @apply py-1.5 pe-3 text-right font-mono tabular-nums text-ink-gray-8;
}
tr > .num:last-child {
  @apply pe-0;
}
</style>
