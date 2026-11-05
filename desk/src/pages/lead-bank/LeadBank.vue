<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <h1 class="truncate text-lg-medium text-ink-gray-9">
          {{ __("Lead Bank") }}
        </h1>
      </template>
      <template #right-header>
        <Button
          v-if="options.data?.is_manager"
          :label="__('Team')"
          @click="router.push({ name: 'LeadBankTeam' })"
        >
          <template #prefix>
            <LucideUsers class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-y-auto overflow-x-hidden">
      <div class="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-5">
        <!-- the one primary action -->
        <section class="flex flex-col gap-2">
          <Button
            variant="solid"
            size="xl"
            class="w-full !h-14 text-lg"
            :label="__('Add a lead')"
            @click="router.push({ name: 'LeadBankAdd' })"
          >
            <template #prefix>
              <LucideCamera class="size-6" aria-hidden="true" />
            </template>
          </Button>
          <p v-if="options.data" class="text-p-sm text-ink-gray-6">
            {{ earnText(options.data) }}
          </p>
        </section>

        <TaskyState
          v-if="mine.error && !data"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load your leads')"
          :message="
            errorText(mine.error, __('Check your connection and try again.'))
          "
        >
          <Button :label="__('Try again')" @click="mine.reload()" />
        </TaskyState>

        <div
          v-else-if="!data"
          class="flex flex-col gap-3"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div class="grid grid-cols-3 gap-3">
            <div
              v-for="i in 3"
              :key="i"
              class="h-[72px] animate-pulse rounded-xl bg-surface-gray-2"
            />
          </div>
          <div class="h-48 animate-pulse rounded-xl bg-surface-gray-2" />
        </div>

        <template v-else>
          <section
            class="grid grid-cols-3 gap-3"
            :aria-label="__('Your totals')"
          >
            <StatTile
              compact
              :label="__('Leads added')"
              :value="data.summary.leads"
            />
            <StatTile compact :label="__('Won')" :value="data.summary.won" />
            <StatTile
              compact
              :label="__('You earned')"
              :value="fullAmount(data.summary.earned, data.currency)"
              :sub="
                data.summary.pending > 0
                  ? __(
                      '{0} on the way',
                      fullAmount(data.summary.pending, data.currency)
                    )
                  : undefined
              "
            />
          </section>

          <TaskyState
            v-if="!data.rows.length"
            :icon="LucideCamera"
            :title="__('You haven\'t added a lead yet')"
            :message="
              __(
                'Spot a shop board, a visiting card or an ad? Take a photo with Add a lead.'
              )
            "
          />

          <ul
            v-else
            role="list"
            class="divide-y divide-outline-gray-1 rounded-xl border border-outline-gray-2 bg-surface-base"
          >
            <li
              v-for="lead in data.rows"
              :key="lead.id"
              class="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3"
            >
              <div class="flex min-w-0 flex-1 flex-col gap-0.5">
                <span class="truncate text-base-medium text-ink-gray-9">{{
                  lead.title
                }}</span>
                <span class="text-p-xs text-ink-gray-6">
                  {{ day(lead.collected_on) }}
                  <template v-if="lead.region">
                    · {{ REGION_LABEL[lead.region] }}</template
                  >
                </span>
              </div>
              <div class="flex flex-col items-end gap-1">
                <TaskyBadge
                  :tone="STATUS_TONE[lead.status]"
                  :label="STATUS_LABEL[lead.status]"
                />
                <span
                  v-if="lead.earned > 0 || lead.pending > 0"
                  class="font-mono text-xs tabular-nums text-ink-gray-7"
                >
                  <template v-if="lead.earned > 0">{{
                    __("Earned {0}", fullAmount(lead.earned, data.currency))
                  }}</template>
                  <template v-if="lead.earned > 0 && lead.pending > 0">
                    ·
                  </template>
                  <template v-if="lead.pending > 0">{{
                    __(
                      "{0} on the way",
                      fullAmount(lead.pending, data.currency)
                    )
                  }}</template>
                </span>
              </div>
            </li>
          </ul>
          <p
            v-if="data.total > data.rows.length"
            class="text-p-sm text-ink-gray-6"
          >
            {{
              __(
                "Showing your latest {0} of {1} leads.",
                String(data.rows.length),
                String(data.total)
              )
            }}
          </p>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { fullAmount } from "@/pages/leads/commission";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed } from "vue";
import { useRouter } from "vue-router";
import LucideCamera from "~icons/lucide/camera";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideUsers from "~icons/lucide/users";
import {
  earnText,
  REGION_LABEL,
  STATUS_LABEL,
  STATUS_TONE,
  type LeadBankOptions,
  type MyLeads,
} from "./leadBank";

const router = useRouter();

const options = createResource<LeadBankOptions>({
  url: "helpdesk.api.lead_bank.get_options",
  auto: true,
});
const mine = createResource<MyLeads>({
  url: "helpdesk.api.lead_bank.get_my_leads",
  auto: true,
});
const data = computed(() => mine.data);

const day = (value: string | null) =>
  value ? dayjs(value).format("D MMM YYYY") : "";
</script>
