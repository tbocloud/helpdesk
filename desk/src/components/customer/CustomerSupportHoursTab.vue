<template>
  <div class="flex flex-col gap-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h2 class="text-lg-semibold text-ink-gray-9">
        {{ __("Support hours") }}
      </h2>
      <div class="flex flex-wrap items-center gap-2">
        <FormControl
          v-if="(data?.contracts.length ?? 0) > 1"
          v-model="contractName"
          type="select"
          class="w-full sm:w-64"
          :aria-label="__('Contract')"
          :options="contractOptions"
        />
        <Button
          v-if="canBill && data"
          variant="subtle"
          :label="__('Create invoice draft')"
          @click="invoicing = true"
        >
          <template #prefix>
            <LucideReceiptText class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <template v-if="data?.can_manage && data.contracts.length">
          <Button
            v-if="data.contract"
            variant="subtle"
            :label="__('Edit contract')"
            @click="openDialog(data.contract)"
          >
            <template #prefix>
              <LucideSquarePen class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <Button
            variant="subtle"
            :label="__('New contract')"
            @click="openDialog(null)"
          >
            <template #prefix>
              <LucidePlus class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </template>
      </div>
    </div>

    <!-- loading -->
    <div
      v-if="usage.loading && !usage.data"
      class="flex flex-col gap-3"
      :aria-label="__('Loading')"
    >
      <span class="h-28 animate-pulse rounded-xl bg-surface-gray-2" />
      <span class="h-40 animate-pulse rounded-lg bg-surface-gray-2" />
    </div>

    <TaskyState
      v-else-if="usage.error && !usage.data && noAccess"
      :icon="LucideLock"
      :title="__('You can\'t see these support hours')"
      :message="
        __(
          'Managers and the people on this customer\'s projects can see them. Ask a project manager to add you to one.'
        )
      "
    />
    <TaskyState
      v-else-if="usage.error && !usage.data"
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load the support hours')"
      :message="
        errorText(usage.error, __('Check your connection and try again.'))
      "
      error
    >
      <Button :label="__('Retry')" @click="usage.reload()" />
    </TaskyState>

    <TaskyState
      v-else-if="data && !data.contracts.length"
      :icon="LucideHourglass"
      :title="__('No support contract')"
      :message="
        data.can_manage
          ? __(
              'Add the hours this customer bought (an AMC, a block of hours or a retainer) to track what is used and be told before they run out.'
            )
          : __(
              'This customer has no AMC or block of support hours. Agent Managers and project managers can add one.'
            )
      "
    >
      <Button
        v-if="data.can_manage"
        variant="solid"
        :label="__('New contract')"
        @click="openDialog(null)"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </TaskyState>

    <template v-else-if="data?.contract">
      <!-- the period that matters now -->
      <section
        v-if="period"
        :aria-label="__('Current period')"
        class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
        :class="usage.loading ? 'opacity-60' : ''"
      >
        <StatTile
          hero
          :label="
            period.is_current
              ? __('This period · {0}', periodText(period))
              : __('Last period · {0}', periodText(period))
          "
          :value="`${period.percent}%`"
          :value-tone="STAGE_TONE[period.stage]"
          :icon="STAGE_ICON[period.stage] ?? LucideHourglass"
          :icon-tone="STAGE_TONE[period.stage]"
          :meter="period.percent"
          :tone="STAGE_TONE[period.stage]"
          :sub="usageText(period)"
        />
        <StatTile
          :label="__('Hours this period')"
          :value="hours(period.allowance)"
          :sub="
            period.carried_in
              ? __(
                  '{0} included + {1} rolled over',
                  hours(period.included),
                  hours(period.carried_in)
                )
              : __('Alert at {0}% used', String(data.contract.alert_threshold))
          "
          :icon="LucideClock"
        />
        <StatTile
          :label="period.is_current ? __('Period ends') : __('Period ended')"
          :value="dayjs(period.end).format('D MMM')"
          :sub="endSub"
          :icon="LucideCalendarClock"
        />
      </section>
      <p
        v-else
        class="flex items-start gap-2 rounded-lg border border-outline-gray-2 px-4 py-3 text-p-sm text-ink-gray-7"
        role="status"
      >
        <LucideCalendarClock
          class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
          aria-hidden="true"
        />
        {{
          __(
            "This contract starts on {0}. Hours logged from then on count against it.",
            dayjs(data.contract.start_date).format("D MMM YYYY")
          )
        }}
      </p>

      <div class="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <!-- where the hours went -->
        <SectionCard
          v-if="period"
          class="lg:col-span-2"
          :title="__('Where the hours went')"
          :description="
            __(
              'Billable time logged in {0}. Non-billable time isn\'t counted.',
              periodText(period)
            )
          "
        >
          <p
            v-if="!period.used"
            class="px-4 py-6 text-center text-p-sm text-ink-gray-6"
          >
            {{ __("No billable time logged in this period yet.") }}
          </p>
          <div
            v-else
            class="grid grid-cols-1 gap-x-6 gap-y-5 px-4 py-4 md:grid-cols-2"
          >
            <div
              v-for="group in breakdownGroups"
              :key="group.key"
              class="min-w-0"
            >
              <h3 class="mb-2 text-sm font-medium text-ink-gray-7">
                {{ group.title }}
              </h3>
              <p v-if="!group.rows.length" class="text-p-sm text-ink-gray-5">
                {{ group.empty }}
              </p>
              <ul v-else role="list" class="flex flex-col gap-2.5">
                <li v-for="row in group.rows" :key="row.key" class="min-w-0">
                  <div
                    class="flex items-baseline justify-between gap-3 text-sm"
                  >
                    <component
                      :is="row.to ? RouterLink : 'span'"
                      :to="row.to"
                      class="min-w-0 truncate"
                      :class="
                        row.to
                          ? 'rounded text-ink-gray-8 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4'
                          : row.muted
                          ? 'text-ink-gray-5'
                          : 'text-ink-gray-8'
                      "
                      :title="row.label"
                    >
                      {{ row.label }}
                    </component>
                    <span
                      class="shrink-0 font-mono text-sm tabular-nums text-ink-gray-8"
                    >
                      {{ hours(row.hours) }}
                    </span>
                  </div>
                  <span
                    class="mt-1 block h-1 overflow-hidden rounded-full bg-surface-gray-2"
                    aria-hidden="true"
                  >
                    <span
                      class="block h-full rounded-full bg-surface-gray-7"
                      :style="{ width: `${share(row.hours)}%` }"
                    />
                  </span>
                </li>
              </ul>
            </div>
          </div>
        </SectionCard>

        <!-- the contract itself -->
        <SectionCard
          :class="period ? '' : 'lg:col-span-3'"
          :title="data.contract.contract_name"
        >
          <template #actions>
            <TaskyBadge
              :label="__(data.contract.status)"
              :tone="data.contract.status === 'Active' ? 'success' : 'neutral'"
              :icon="
                data.contract.status === 'Active'
                  ? LucideCircleCheck
                  : undefined
              "
            />
          </template>
          <dl
            class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 px-4 py-4 text-sm"
          >
            <template v-for="item in contractDetails" :key="item.label">
              <dt class="text-ink-gray-5">{{ item.label }}</dt>
              <dd
                class="min-w-0 break-words text-right text-ink-gray-8 tabular-nums"
              >
                {{ item.value }}
              </dd>
            </template>
          </dl>
          <p
            v-if="data.contract.notes"
            class="whitespace-pre-line border-t border-outline-gray-1 px-4 py-3 text-p-sm text-ink-gray-7"
          >
            {{ data.contract.notes }}
          </p>
        </SectionCard>
      </div>

      <!-- every period so far -->
      <SectionCard
        v-if="data.periods.length > 1"
        :title="__('Periods')"
        :count="data.periods.length"
        :description="
          __('Newest first. Hours count by the day the work was done.')
        "
      >
        <table class="hidden w-full text-sm md:table">
          <caption class="sr-only">
            {{
              __("Support hours per period")
            }}
          </caption>
          <thead>
            <tr
              class="border-b border-outline-gray-2 bg-surface-gray-1 text-left text-xs text-ink-gray-5"
            >
              <th scope="col" class="px-4 py-2 font-normal">
                {{ __("Period") }}
              </th>
              <th scope="col" class="px-3 py-2 text-right font-normal">
                {{ __("Hours") }}
              </th>
              <th scope="col" class="px-3 py-2 text-right font-normal">
                {{ __("Used") }}
              </th>
              <th scope="col" class="px-3 py-2 text-right font-normal">
                {{ __("Left") }}
              </th>
              <th scope="col" class="w-1/4 px-4 py-2 font-normal">
                <span class="sr-only">{{ __("Share used") }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in data.periods"
              :key="p.start"
              class="border-b border-outline-gray-1 last:border-b-0"
            >
              <th
                scope="row"
                class="px-4 py-2.5 text-left font-normal text-ink-gray-8"
              >
                {{ periodText(p) }}
                <span
                  v-if="p.is_current"
                  class="ml-1.5 text-xs text-ink-gray-5"
                >
                  {{ __("Current") }}
                </span>
              </th>
              <td
                class="px-3 py-2.5 text-right font-mono tabular-nums text-ink-gray-8"
              >
                {{ hours(p.allowance) }}
              </td>
              <td
                class="px-3 py-2.5 text-right font-mono tabular-nums text-ink-gray-8"
              >
                {{ hours(p.used) }}
              </td>
              <td
                class="px-3 py-2.5 text-right font-mono tabular-nums"
                :class="p.remaining < 0 ? 'text-danger' : 'text-ink-gray-8'"
              >
                {{
                  p.remaining < 0
                    ? __("{0} over", hours(-p.remaining))
                    : hours(p.remaining)
                }}
              </td>
              <td class="px-4 py-2.5">
                <SupportHoursMeter :period="p" :label="periodText(p)" />
              </td>
            </tr>
          </tbody>
        </table>
        <ul role="list" class="md:hidden">
          <li
            v-for="p in data.periods"
            :key="p.start"
            class="flex flex-col gap-1.5 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
          >
            <div class="flex items-baseline justify-between gap-3 text-sm">
              <span class="text-ink-gray-8">
                {{ periodText(p) }}
                <span v-if="p.is_current" class="ml-1 text-xs text-ink-gray-5">
                  {{ __("Current") }}
                </span>
              </span>
              <span class="font-mono tabular-nums text-ink-gray-8">
                {{ p.percent }}%
              </span>
            </div>
            <SupportHoursMeter :period="p" :label="periodText(p)" />
            <span
              class="text-xs tabular-nums"
              :class="p.remaining < 0 ? 'text-danger' : 'text-ink-gray-6'"
            >
              {{ usageText(p) }}
            </span>
          </li>
        </ul>
      </SectionCard>
    </template>

    <InvoiceList
      v-if="canBill && data"
      ref="invoiceList"
      :customer="customer"
    />
    <InvoiceDraftDialog
      v-if="invoicing"
      v-model:open="invoicing"
      :customer="customer"
      @created="invoiceList?.reload()"
    />

    <SupportContractDialog
      v-if="dialog.open"
      v-model:open="dialog.open"
      :customer="customer"
      :contract="dialog.contract"
      @saved="onSaved"
    />
  </div>
</template>

<script setup lang="ts">
import SupportContractDialog from "@/components/customer/SupportContractDialog.vue";
import SupportHoursMeter from "@/components/customer/SupportHoursMeter.vue";
import InvoiceDraftDialog from "@/components/invoicing/InvoiceDraftDialog.vue";
import InvoiceList from "@/components/invoicing/InvoiceList.vue";
import SectionCard from "@/components/SectionCard.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import {
  hours,
  periodText,
  STAGE_ICON,
  STAGE_TONE,
  usageText,
  type SupportContract,
  type UsagePeriod,
} from "@/composables/supportHours";
import { useAuthStore } from "@/stores/auth";
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs, FormControl } from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideLock from "~icons/lucide/lock";
import LucidePlus from "~icons/lucide/plus";
import LucideReceiptText from "~icons/lucide/receipt-text";
import LucideSquarePen from "~icons/lucide/square-pen";

/** `name` is empty for time outside a project, or (`other`) for records the viewer can't open */
interface BreakdownRow {
  name: string | null;
  label: string | null;
  hours: number;
  other?: 1;
}

interface CustomerSupportHours {
  can_manage: boolean;
  contracts: Pick<
    SupportContract,
    | "name"
    | "contract_name"
    | "contract_type"
    | "status"
    | "start_date"
    | "end_date"
  >[];
  contract: SupportContract | null;
  period: UsagePeriod | null;
  periods: UsagePeriod[];
  breakdown: {
    projects: BreakdownRow[];
    tickets: BreakdownRow[];
    people: BreakdownRow[] | null;
  } | null;
}

const props = defineProps<{ customer: string }>();

const route = useRoute();
const router = useRouter();
const { getUser } = useUserStore();
const auth = useAuthStore();

// only Agent Managers and System Managers bill (the server checks the same)
const canBill = computed(() => auth.isAdmin || auth.isManager);
const invoicing = ref(false);
const invoiceList = ref<InstanceType<typeof InvoiceList> | null>(null);

// the contract on screen, in the URL so a link opens the same one
const contractName = ref(
  typeof route.query.contract === "string" ? route.query.contract : ""
);

const usage = createResource({
  url: "helpdesk.api.support_contracts.get_customer_support_hours",
  makeParams: () => ({
    customer: props.customer,
    contract: contractName.value || undefined,
  }),
  auto: true,
  onSuccess(result: CustomerSupportHours) {
    if (!contractName.value && result.contract)
      contractName.value = result.contract.name;
    // a link to a contract that isn't this customer's: show today's instead
    else if (contractName.value && !result.contract && result.contracts.length)
      contractName.value = "";
  },
});

watch(contractName, (name, previous) => {
  router.replace({
    query: { ...route.query, contract: name || undefined },
    hash: route.hash,
  });
  // the first answer picks today's contract; only a real switch reloads
  if (previous) usage.reload();
});

const data = computed<CustomerSupportHours | null>(() => usage.data ?? null);
const period = computed(() => data.value?.period ?? null);
const noAccess = computed(
  () =>
    (usage.error as { exc_type?: string } | null)?.exc_type ===
    "PermissionError"
);

const contractOptions = computed(() =>
  (data.value?.contracts ?? []).map((c) => ({
    label: `${c.contract_name} · ${__(c.status)}`,
    value: c.name,
  }))
);

const endSub = computed(() => {
  const p = period.value;
  if (!p) return "";
  if (!p.is_current) return dayjs(p.end).format("D MMM YYYY");
  const days = dayjs(p.end).diff(dayjs().startOf("day"), "day");
  return days === 0
    ? __("Today")
    : days === 1
    ? __("Tomorrow")
    : __("In {0} days", String(days));
});

const contractDetails = computed(() => {
  const c = data.value?.contract;
  if (!c) return [];
  const rows = [
    { label: __("Type"), value: __(c.contract_type) },
    { label: __("Billing period"), value: __(c.billing_period) },
    {
      label: __("Dates"),
      value: periodText({ start: c.start_date, end: c.end_date }),
    },
    {
      label:
        c.billing_period === "One-off block"
          ? __("Hours in the block")
          : __("Hours per period"),
      value: hours(c.hours_per_period),
    },
  ];
  if (c.billing_period !== "One-off block")
    rows.push({
      label: __("Unused hours"),
      value: c.rollover_unused ? __("Roll over") : __("Lapse"),
    });
  rows.push({ label: __("Alert at"), value: `${c.alert_threshold}%` });
  if (c.account_manager)
    rows.push({
      label: __("Account manager"),
      value: getUser(c.account_manager)?.full_name || c.account_manager,
    });
  if (c.rate_per_extra_hour)
    rows.push({
      label: __("Extra hours"),
      value: __(
        "{0} an hour",
        `${c.currency ? `${c.currency} ` : ""}${c.rate_per_extra_hour}`
      ),
    });
  return rows;
});

const breakdownGroups = computed(() => {
  const b = data.value?.breakdown;
  if (!b) return [];
  const groups = [
    {
      key: "projects",
      title: __("By project"),
      empty: __("No time on projects."),
      rows: b.projects.map((r) => ({
        key: r.name || (r.other ? "other" : "none"),
        label: r.other
          ? __("Projects you aren't on")
          : r.name
          ? r.label || r.name
          : __("No project"),
        hours: r.hours,
        muted: !r.name,
        to: r.name
          ? { name: "TaskyProject", params: { projectId: r.name } }
          : undefined,
      })),
    },
    {
      key: "tickets",
      title: __("By ticket"),
      empty: __("No time on tasks from this customer's tickets."),
      rows: b.tickets.map((r) => ({
        key: r.name || "other",
        label: r.name
          ? `#${r.name} ${r.label || ""}`.trim()
          : __("Tickets you can't open"),
        hours: r.hours,
        muted: !r.name,
        to: r.name
          ? { name: "TicketAgent", params: { ticketId: r.name } }
          : undefined,
      })),
    },
  ];
  if (b.people)
    groups.push({
      key: "people",
      title: __("By person"),
      empty: __("Nobody logged time."),
      rows: b.people.map((r) => ({
        key: r.name || "other",
        label: r.label || r.name || __("Unknown"),
        hours: r.hours,
        muted: false,
        to: undefined,
      })),
    });
  return groups;
});

function share(value: number) {
  const used = period.value?.used || 0;
  return used ? Math.round((value / used) * 100) : 0;
}

const dialog = reactive<{ open: boolean; contract: SupportContract | null }>({
  open: false,
  contract: null,
});

function openDialog(contract: SupportContract | null) {
  dialog.contract = contract;
  dialog.open = true;
}

function onSaved(name: string) {
  if (contractName.value === name) usage.reload();
  else contractName.value = name;
}
</script>
