<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Expenses')"
      :subtitle="
        __('Claim what you spent for work, and decide the claims sent to you.')
      "
    >
      <template #right-header>
        <Button
          size="md"
          :loading="expenses.loading && !!page"
          :aria-label="__('Refresh expenses')"
          @click="reload"
        >
          <template #icon>
            <LucideRefreshCw class="size-[18px]" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-if="page?.employee"
          variant="solid"
          size="md"
          :label="__('New claim')"
          @click="showNew = true"
        >
          <template #prefix>
            <LucidePlus class="size-[18px]" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="relative flex-1 overflow-y-auto overflow-x-hidden">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <TaskyState
          v-if="expenses.error && !page"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :error="!isRefusal"
          :icon="isRefusal ? LucideLock : LucideCircleAlert"
          :title="
            isRefusal
              ? __('Expenses aren\'t open to you')
              : __('Couldn\'t load your expenses')
          "
          :message="
            errorText(
              expenses.error,
              __('Check your connection and try again.')
            )
          "
        >
          <Button v-if="!isRefusal" :label="__('Try again')" @click="reload" />
        </TaskyState>

        <div
          v-else-if="!page"
          class="flex flex-col gap-4"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div class="h-10 w-64 animate-pulse rounded-full bg-surface-gray-3" />
          <div class="h-64 animate-pulse rounded-xl bg-surface-gray-3" />
        </div>

        <TaskyState
          v-else-if="!page.available"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :icon="LucideReceipt"
          :title="__('Expenses aren\'t on the ERP site yet')"
          :message="
            __(
              'They need the latest TBO Smart there. Ask an admin to update it.'
            )
          "
        />

        <template v-else>
          <ViewTabs
            v-if="page.can_approve"
            :model-value="view"
            :options="tabs"
            :aria-label="__('Expense views')"
            @update:model-value="pickView"
          />

          <ClaimApprovals
            v-if="view === 'approve'"
            :approvals="page.approvals || []"
            :currency="currency"
            @decided="reload"
          />

          <TaskyState
            v-else-if="!page.employee"
            class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
            :icon="LucideUserX"
            :title="__('You aren\'t linked to an employee on the ERP site')"
            :message="
              __(
                'Ask HR to put your email as the User ID on your Employee record there. Then you can claim expenses here.'
              )
            "
          />

          <section
            v-else
            class="rounded-xl border border-outline-gray-2 bg-surface-base"
            :aria-label="__('My claims')"
          >
            <TaskyState
              v-if="!claims.length"
              class="py-10"
              :icon="LucideReceipt"
              :title="__('No claims yet')"
              :message="
                __(
                  'Spent money for work? Use New claim, add a photo of the bill, and it goes to your approver.'
                )
              "
            />

            <template v-else>
              <ul class="divide-y divide-outline-gray-1">
                <li
                  v-for="claim in claims"
                  :key="claim.name"
                  class="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center"
                >
                  <div class="min-w-0 flex-1">
                    <p class="truncate text-base font-medium text-ink-gray-9">
                      {{ claim.expense_type }}
                      <span
                        v-if="claim.description"
                        class="font-normal text-ink-gray-6"
                      >
                        · {{ claim.description }}
                      </span>
                    </p>
                    <p class="truncate text-sm text-ink-gray-6">
                      {{ dayjs(claim.date).format("D MMM YYYY") }}
                      · <span class="font-mono">{{ claim.name }}</span>
                      <template v-if="claim.approver">
                        · {{ __("Approver: {0}", claim.approver) }}
                      </template>
                    </p>
                  </div>
                  <div class="flex items-center gap-3 sm:justify-end">
                    <TaskyBadge v-bind="claimLook(claim.status)" />
                    <span
                      class="font-mono text-base font-semibold tabular-nums text-ink-gray-9"
                    >
                      {{ money(claim.amount, currency) }}
                    </span>
                    <Button
                      v-if="claim.receipt"
                      :link="receiptUrl(claim.name, claim.receipt)"
                      :aria-label="__('Open the receipt of {0}', claim.name)"
                      :tooltip="__('Receipt')"
                    >
                      <template #icon>
                        <LucideReceipt class="size-4" aria-hidden="true" />
                      </template>
                    </Button>
                  </div>
                </li>
              </ul>
              <div
                v-if="page.claims?.has_more"
                class="flex justify-center border-t border-outline-gray-1 px-4 py-3.5"
              >
                <Button
                  :label="__('Show older claims')"
                  :loading="expenses.loading"
                  @click="showMore"
                />
              </div>
            </template>
          </section>
        </template>
      </div>
    </div>

    <NewClaimDialog
      v-if="page?.employee"
      v-model:open="showNew"
      :types="page.types || []"
      :currency="currency"
      @created="reload"
    />
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import ViewTabs from "@/components/ViewTabs.vue";
import { money } from "@/components/invoicing/invoices";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs } from "frappe-ui";
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideLock from "~icons/lucide/lock";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideReceipt from "~icons/lucide/receipt";
import LucideUserX from "~icons/lucide/user-x";
import ClaimApprovals from "./ClaimApprovals.vue";
import NewClaimDialog from "./NewClaimDialog.vue";
import {
  claimLook,
  receiptUrl,
  type Claim,
  type ExpensesPage,
} from "./expenses";

const route = useRoute();
const router = useRouter();
const showNew = ref(false);

// older pages of the person's claims, kept as "Show older claims" adds them
const claimPage = ref(1);
const claims = ref<Claim[]>([]);

const expenses = createResource<ExpensesPage>({
  url: "helpdesk.api.expenses.get_expenses",
  makeParams: () => ({ page: claimPage.value }),
  auto: true,
  onSuccess(data: ExpensesPage) {
    const rows = data.claims?.data || [];
    claims.value = claimPage.value === 1 ? rows : [...claims.value, ...rows];
  },
});
// the last answer, kept while a reload runs so the page doesn't flash
const page = computed(() => expenses.data as ExpensesPage | null);
const currency = computed(() => page.value?.currency || "INR");
const isRefusal = computed(
  () => expenses.error?.exc_type === "PermissionError"
);

// the view is in the URL, so a link from a notification opens the approvals
const view = computed(() =>
  page.value?.can_approve && route.query.view === "approve" ? "approve" : "mine"
);
const tabs = computed(() => [
  { value: "mine", label: __("My claims") },
  {
    value: "approve",
    label: __("To approve"),
    count: page.value?.approvals?.length ?? 0,
  },
]);
function pickView(value: string) {
  router.replace({
    query: {
      ...route.query,
      view: value === "approve" ? "approve" : undefined,
    },
  });
}

function reload() {
  claimPage.value = 1;
  expenses.reload();
}
function showMore() {
  claimPage.value += 1;
  expenses.reload();
}
</script>
