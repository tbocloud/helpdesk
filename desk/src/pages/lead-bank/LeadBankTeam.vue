<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <nav
          class="flex min-w-0 items-center gap-1.5 text-lg-medium"
          :aria-label="__('Breadcrumb')"
        >
          <router-link
            :to="{ name: 'LeadBank' }"
            class="shrink-0 rounded text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            >{{ __("Lead Bank") }}</router-link
          >
          <LucideChevronRight
            class="size-4 shrink-0 text-ink-gray-4"
            aria-hidden="true"
          />
          <h1 class="truncate text-ink-gray-9">{{ __("Team") }}</h1>
        </nav>
      </template>
      <template #right-header>
        <Button :label="__('Move credit')" @click="openCredit">
          <template #prefix>
            <LucideArrowRightLeft class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-y-auto overflow-x-hidden">
      <div
        class="mx-auto flex w-full max-w-5xl flex-col gap-5 px-4 py-5 md:px-6"
      >
        <div class="flex flex-wrap items-end gap-3">
          <FormControl
            v-model="month"
            type="select"
            class="w-full sm:w-56"
            :label="__('Month')"
            :options="monthOptions"
          />
        </div>

        <TaskyState
          v-if="page.error && !data"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the Lead Bank')"
          :message="
            errorText(page.error, __('Check your connection and try again.'))
          "
        >
          <Button
            :label="__('Try again')"
            @click="page.submit({ month: `${month}-01` })"
          />
        </TaskyState>

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
          <section
            class="grid grid-cols-2 gap-3 md:grid-cols-4"
            :aria-label="__('Totals')"
          >
            <StatTile
              compact
              :label="__('Leads collected')"
              :value="data.collected"
            />
            <StatTile
              compact
              :label="__('Won')"
              :value="data.won"
              :sub="__('{0}% of collected', String(data.conversion))"
            />
            <StatTile
              compact
              :label="__('Referral due')"
              :value="fullAmount(data.referral.due, data.currency)"
              :sub="
                __(
                  '{0} earned, {1} paid',
                  fullAmount(data.referral.earned, data.currency),
                  fullAmount(data.referral.paid, data.currency)
                )
              "
            />
            <StatTile
              compact
              :label="__('Waiting for a department')"
              :value="data.pool.count"
            />
          </section>

          <section
            class="rounded-xl border border-outline-gray-2 bg-surface-base"
            :aria-label="__('By region')"
          >
            <h2
              class="border-b border-outline-gray-1 px-4 py-3 text-base-medium text-ink-gray-9"
            >
              {{ __("By region") }}
            </h2>
            <table class="w-full text-sm">
              <thead class="text-left text-xs text-ink-gray-6">
                <tr>
                  <th class="px-4 py-2 font-normal">{{ __("Region") }}</th>
                  <th class="px-2 py-2 font-normal">{{ __("Department") }}</th>
                  <th class="px-2 py-2 text-right font-normal">
                    {{ __("Collected") }}
                  </th>
                  <th class="px-4 py-2 text-right font-normal">
                    {{ __("Won") }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in data.by_region"
                  :key="row.region"
                  class="border-t border-outline-gray-1"
                >
                  <td class="px-4 py-2 text-ink-gray-9">
                    {{ REGION_LABEL[row.region] }}
                  </td>
                  <td class="px-2 py-2 text-ink-gray-7">
                    {{ row.department || __("None, goes to the waiting list") }}
                  </td>
                  <td class="px-2 py-2 text-right font-mono tabular-nums">
                    {{ row.collected }}
                  </td>
                  <td class="px-4 py-2 text-right font-mono tabular-nums">
                    {{ row.won }}
                  </td>
                </tr>
              </tbody>
            </table>
          </section>

          <section
            class="rounded-xl border border-outline-gray-2 bg-surface-base"
            :aria-label="__('Top collectors')"
          >
            <h2
              class="border-b border-outline-gray-1 px-4 py-3 text-base-medium text-ink-gray-9"
            >
              {{ __("Top collectors") }}
            </h2>
            <p
              v-if="!data.collectors.length"
              class="px-4 py-6 text-center text-p-sm text-ink-gray-6"
            >
              {{ __("Nobody has added a lead in {0} yet.", monthTitle(month)) }}
            </p>
            <table v-else class="w-full text-sm">
              <thead class="text-left text-xs text-ink-gray-6">
                <tr>
                  <th class="px-4 py-2 font-normal">{{ __("Person") }}</th>
                  <th class="px-2 py-2 text-right font-normal">
                    {{ __("Collected") }}
                  </th>
                  <th class="px-2 py-2 text-right font-normal">
                    {{ __("Won") }}
                  </th>
                  <th class="px-4 py-2 text-right font-normal">
                    {{ __("Referral due") }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="person in data.collectors"
                  :key="person.user"
                  class="border-t border-outline-gray-1"
                >
                  <td class="px-4 py-2 text-ink-gray-9">
                    {{ person.full_name }}
                  </td>
                  <td class="px-2 py-2 text-right font-mono tabular-nums">
                    {{ person.collected }}
                  </td>
                  <td class="px-2 py-2 text-right font-mono tabular-nums">
                    {{ person.won }}
                  </td>
                  <td class="px-4 py-2 text-right font-mono tabular-nums">
                    {{ fullAmount(dueOf(person.user), data.currency) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </section>

          <section
            v-if="data.pool.count"
            class="rounded-xl border border-outline-gray-2 bg-surface-base"
            :aria-label="__('Waiting for a department')"
          >
            <h2
              class="border-b border-outline-gray-1 px-4 py-3 text-base-medium text-ink-gray-9"
            >
              {{ __("Waiting for a department") }}
              <span
                class="ml-1 font-mono text-xs tabular-nums text-ink-gray-5"
                >{{ data.pool.count }}</span
              >
            </h2>
            <p class="px-4 pt-3 text-p-sm text-ink-gray-6">
              {{
                __(
                  "These regions have no department yet, so nobody owns these leads. Set the department in Settings → CRM → Commission plans → Referral (Lead Bank), then give each lead to someone."
                )
              }}
            </p>
            <ul role="list" class="divide-y divide-outline-gray-1">
              <li
                v-for="lead in data.pool.leads"
                :key="lead.lead"
                class="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3"
              >
                <router-link
                  :to="{ name: 'Lead', params: { leadId: lead.lead } }"
                  class="min-w-0 flex-1 truncate rounded text-base-medium text-brand-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                  >{{ lead.title }}</router-link
                >
                <span class="text-p-xs text-ink-gray-6">
                  {{ lead.region ? REGION_LABEL[lead.region] : "" }} ·
                  {{ lead.collected_by_name }}
                </span>
              </li>
            </ul>
          </section>
        </template>
      </div>
    </div>
  </div>

  <Dialog v-model:open="showCredit" :title="__('Move credit')">
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="moveCredit"
    >
      <p class="text-p-sm text-ink-gray-6">
        {{
          __(
            "The referral for a lead goes to someone else from now on. Statements already approved stay as they are."
          )
        }}
      </p>
      <FormControl
        v-model="credit.lead"
        :label="__('Lead (for example CRM-LEAD-2026-00012)')"
        autocomplete="off"
        required
      />
      <FormControl
        v-model="credit.user"
        type="select"
        :label="__('New collector')"
        :options="userOptions"
      />
      <FormControl
        v-model="credit.reason"
        type="textarea"
        :rows="2"
        :label="__('Why is it moving?')"
        required
      />
      <p
        v-if="creditError"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ creditError }}</span>
      </p>
    </form>
    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Move credit')"
          :loading="moving"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { fullAmount, monthTitle, monthValue } from "@/pages/leads/commission";
import { useAgentStore } from "@/stores/agent";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  createResource,
  Dialog,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, onMounted, reactive, ref, useId, watch } from "vue";
import LucideArrowRightLeft from "~icons/lucide/arrow-right-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import { REGION_LABEL, type Dashboard } from "./leadBank";

const { agents } = useAgentStore();
const formId = `lead-bank-credit-${useId()}`;
const month = ref(monthValue());
// this month and the five before
const monthOptions = Array.from({ length: 6 }, (_, i) => {
  const value = monthValue(-i);
  return { label: monthTitle(value), value };
});

const page = createResource<Dashboard>({
  url: "helpdesk.api.lead_bank.get_dashboard",
  params: { month: `${month.value}-01` },
  auto: true,
});
const data = computed(() => page.data);
// a changed month is a new question
watch(month, (value) => page.submit({ month: `${value}-01` }));

const dueOf = (user: string) =>
  data.value?.referral.by_collector.find((p) => p.user === user)?.due ?? 0;

const showCredit = ref(false);
const moving = ref(false);
const creditError = ref("");
const credit = reactive({ lead: "", user: "", reason: "" });
const userOptions = computed(() => [
  { label: __("Pick a person"), value: "" },
  ...(agents.data ?? [])
    .filter((a: { user?: string }) => a.user)
    .map((a: { user: string; agent_name?: string }) => ({
      label: a.agent_name ? `${a.agent_name} (${a.user})` : a.user,
      value: a.user,
    })),
]);

onMounted(() => {
  if (!agents.loading && !agents.data?.length && !agents.list.promise)
    agents.fetch();
});

function openCredit() {
  Object.assign(credit, { lead: "", user: "", reason: "" });
  creditError.value = "";
  showCredit.value = true;
}

function moveCredit() {
  if (moving.value) return;
  if (!credit.lead.trim() || !credit.user || !credit.reason.trim()) {
    creditError.value = __("Give the lead, the new person and the reason.");
    return;
  }
  creditError.value = "";
  moving.value = true;
  call("helpdesk.api.lead_bank.reassign_credit", {
    lead: credit.lead.trim(),
    user: credit.user,
    reason: credit.reason.trim(),
  })
    .then(() => {
      toast.success(__("Credit moved"));
      showCredit.value = false;
      page.reload();
    })
    // the ERP site's own reason, e.g. a lead that wasn't added through the Lead Bank
    .catch((e: unknown) => {
      creditError.value = errorText(
        e,
        __("Couldn't move the credit. Check your connection and try again.")
      );
    })
    .finally(() => (moving.value = false));
}
</script>
