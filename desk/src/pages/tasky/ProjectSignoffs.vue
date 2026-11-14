<template>
  <div class="flex h-full flex-col">
    <ProjectNav :project-id="projectId">
      <template #actions>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="signoffs.loading && !!signoffs.data"
          @click="signoffs.reload()"
        >
          <template #icon><LucideRefreshCw class="size-4" /></template>
        </Button>
      </template>
    </ProjectNav>

    <div class="relative flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-5xl px-4 py-5 md:px-6">
        <TaskyState
          v-if="signoffs.error && !signoffs.data"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the sign-offs')"
          :message="loadErrorMessage(signoffs.error)"
        >
          <Button :label="__('Retry')" @click="signoffs.reload()" />
        </TaskyState>

        <template v-else>
          <div class="mb-4 flex flex-wrap items-center gap-2">
            <h2 class="text-lg-semibold text-ink-gray-9">
              {{ __("Sign-offs") }}
            </h2>
            <div class="ml-auto flex flex-wrap gap-2">
              <Button
                v-if="data?.can_create_uat"
                :variant="hasUat ? 'subtle' : 'solid'"
                :label="__('New UAT sign-off')"
                @click="newSignoff(true)"
              >
                <template #prefix>
                  <LucideListChecks class="size-4" aria-hidden="true" />
                </template>
              </Button>
              <Button
                v-if="data?.can_create && data.signoffs.length"
                :label="__('New sign-off')"
                @click="newSignoff(false)"
              >
                <template #prefix>
                  <LucidePlus class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </div>
          </div>

          <!-- roll-up: every sign-off, training and UAT -->
          <div
            v-if="!data || data.signoffs.length"
            class="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3"
          >
            <StatTile
              compact
              :label="__('Signed off')"
              :value="
                data
                  ? __(
                      '{0} of {1}',
                      String(signedCount),
                      String(counted.length)
                    )
                  : ''
              "
              :icon="LucideCircleCheck"
              :icon-tone="allSigned ? 'success' : 'neutral'"
              :meter="
                data && counted.length
                  ? (signedCount / counted.length) * 100
                  : null
              "
              :tone="allSigned ? 'success' : 'neutral'"
              :loading="!data"
            />
            <StatTile
              compact
              :label="__('Needs clarification')"
              :value="followUpCount"
              :sub="
                followUpCount
                  ? __('Items marked Not clear or escalated')
                  : __('Nothing waiting on us')
              "
              :icon="LucideCircleHelp"
              :icon-tone="followUpCount ? 'warning' : 'neutral'"
              :loading="!data"
            />
            <StatTile
              compact
              :label="__('With the customer')"
              :value="withCustomerCount"
              :sub="__('Sent and not signed off yet')"
              :icon="LucideSend"
              :loading="!data"
            />
          </div>

          <!-- what holds up each sign-off not signed yet, in words -->
          <section
            v-if="waiting.length"
            class="mb-4 rounded-lg border border-outline-gray-2 bg-surface-base"
            :aria-labelledby="waitingHeading"
          >
            <h3
              :id="waitingHeading"
              class="border-b border-outline-gray-1 px-4 py-2 text-sm font-medium text-ink-gray-8"
            >
              {{ __("Waiting on") }}
            </h3>
            <ul role="list">
              <li
                v-for="w in waiting"
                :key="w.name"
                class="border-b border-outline-gray-1 last:border-b-0"
              >
                <router-link
                  :to="{
                    name: 'TaskySignoff',
                    params: { projectId, signoffId: w.name },
                  }"
                  class="flex min-h-[44px] flex-wrap items-center gap-x-2 gap-y-0.5 px-4 py-2 text-sm hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
                >
                  <component
                    :is="w.onUs ? LucideCircleHelp : LucideClock"
                    class="size-4 shrink-0"
                    :class="w.onUs ? 'text-warning' : 'text-ink-gray-5'"
                    aria-hidden="true"
                  />
                  <span class="font-medium text-ink-gray-9">{{ w.title }}</span>
                  <span class="text-ink-gray-6">{{ w.reason }}</span>
                </router-link>
              </li>
            </ul>
          </section>

          <div
            v-if="data?.completion_letter"
            class="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-base px-4 py-3"
          >
            <LucideBadgeCheck
              class="size-5 shrink-0 text-success"
              aria-hidden="true"
            />
            <div class="min-w-0 flex-1">
              <p class="text-base-medium text-ink-gray-9">
                {{ __("All training signed off") }}
              </p>
              <p class="text-p-sm text-ink-gray-6">
                {{
                  __(
                    "The project completion letter is on the project and was emailed to the signatories."
                  )
                }}
              </p>
            </div>
            <a
              :href="data.completion_letter.file_url"
              target="_blank"
              rel="noopener"
              class="inline-flex h-8 items-center gap-1.5 rounded-md border border-outline-gray-2 bg-surface-base px-3 text-sm font-medium text-ink-gray-8 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >
              <LucideDownload class="size-4" aria-hidden="true" />
              {{ __("Completion letter") }}
            </a>
          </div>

          <!-- Loading -->
          <div
            v-if="!data"
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            aria-busy="true"
            :aria-label="__('Loading')"
          >
            <div
              v-for="i in 3"
              :key="i"
              class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-4 last:border-b-0"
            >
              <div class="flex flex-1 flex-col gap-2">
                <div
                  class="h-3.5 w-1/3 animate-pulse rounded bg-surface-gray-2"
                />
                <div
                  class="h-3 w-1/2 animate-pulse rounded bg-surface-gray-2"
                />
              </div>
              <div class="h-2 w-24 animate-pulse rounded bg-surface-gray-2" />
            </div>
          </div>

          <TaskyState
            v-else-if="!data.signoffs.length"
            :icon="LucideClipboardCheck"
            :title="__('No sign-offs yet')"
            :message="
              data.can_create
                ? __(
                    'Send the customer a sign-off for each stage: a module\'s training, UAT, go-live. They reply to accept it, and you mark it signed off.'
                  )
                : __(
                    'Sign-offs for this project\'s trainings show up here once the project lead or manager creates them.'
                  )
            "
          >
            <Button
              v-if="data.can_create"
              :variant="data.can_create_uat ? 'subtle' : 'solid'"
              :label="__('New sign-off')"
              @click="newSignoff(false)"
            >
              <template #prefix>
                <LucidePlus class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </TaskyState>

          <template v-else>
            <div class="-mx-1 mb-3 min-w-0 overflow-x-auto px-1">
              <TabButtons
                :model-value="statusFilter"
                size="md"
                :aria-label="__('Filter sign-offs by status')"
                :aria-controls="listId"
                :options="
                  STATUS_TABS.map((t) => ({
                    label: t === 'All' ? __('All') : __(t),
                    value: t,
                  }))
                "
                @update:model-value="(v: string) => (statusFilter = v)"
              >
                <template #suffix="{ button, checked }">
                  <span
                    class="font-mono text-xs tabular-nums"
                    :class="checked ? '' : 'text-ink-gray-5'"
                    >{{ countFor(button.modelValue) }}</span
                  >
                </template>
              </TabButtons>
            </div>

            <div
              :id="listId"
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            >
              <!-- the columns of TBO's Sign-off requirements; on a phone each row stacks -->
              <div
                class="hidden border-b border-outline-gray-2 px-4 py-2 text-xs text-ink-gray-5 md:grid md:grid-cols-[minmax(0,1.6fr)_minmax(0,1.2fr)_8.5rem_6.5rem_6.5rem] md:gap-4"
                aria-hidden="true"
              >
                <span>{{ __("Sign-off · template") }}</span>
                <span>{{ __("Recipient") }}</span>
                <span>{{ __("Status") }}</span>
                <span>{{ __("Sent on") }}</span>
                <span>{{ __("Signed off on") }}</span>
              </div>
              <p
                v-if="!shown.length"
                class="px-4 py-6 text-center text-p-sm text-ink-gray-6"
              >
                {{
                  __("No sign-offs are {0}.", __(statusFilter).toLowerCase())
                }}
              </p>
              <ul v-else role="list" :aria-label="__('Sign-offs')">
                <li
                  v-for="s in shown"
                  :key="s.name"
                  class="border-b border-outline-gray-1 last:border-b-0"
                >
                  <router-link
                    :to="{
                      name: 'TaskySignoff',
                      params: { projectId, signoffId: s.name },
                    }"
                    class="flex flex-col gap-1.5 px-4 py-3 transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight md:grid md:grid-cols-[minmax(0,1.6fr)_minmax(0,1.2fr)_8.5rem_6.5rem_6.5rem] md:items-center md:gap-4"
                  >
                    <div class="flex min-w-0 flex-col gap-0.5">
                      <div class="flex min-w-0 items-center gap-2">
                        <span
                          class="truncate text-base-medium text-ink-gray-9"
                          >{{ s.module_title || s.template || s.name }}</span
                        >
                        <TaskyBadge
                          v-if="s.signoff_type === 'UAT'"
                          :label="__('UAT')"
                          :icon="LucideListChecks"
                        />
                      </div>
                      <span class="truncate text-xs text-ink-gray-6">
                        {{ s.template || __("No template") }}
                        <template v-if="s.follow_up">
                          ·
                          <span class="font-medium text-warning">{{
                            s.signoff_type === "UAT"
                              ? s.follow_up === 1
                                ? __("1 open issue")
                                : __("{0} open issues", String(s.follow_up))
                              : s.follow_up === 1
                              ? __("1 to clarify")
                              : __("{0} to clarify", String(s.follow_up))
                          }}</span>
                        </template>
                      </span>
                    </div>
                    <span class="min-w-0 truncate text-sm text-ink-gray-8">
                      {{ s.signatory_name || "—" }}
                      <span
                        v-if="s.signatory_email"
                        class="block truncate font-mono text-xs text-ink-gray-5"
                        >{{ s.signatory_email }}</span
                      >
                    </span>
                    <span>
                      <TaskyBadge
                        :label="__(signoffStatusMeta(s.customer_status).label)"
                        :tone="signoffStatusMeta(s.customer_status).tone"
                        :icon="signoffStatusMeta(s.customer_status).icon"
                      />
                    </span>
                    <span class="text-xs tabular-nums text-ink-gray-7">
                      <span class="text-ink-gray-5 md:hidden"
                        >{{ __("Sent on") }}:
                      </span>
                      {{
                        s.link_sent_on
                          ? dateFormat(s.link_sent_on, "D MMM YYYY")
                          : "—"
                      }}
                    </span>
                    <span class="text-xs tabular-nums text-ink-gray-7">
                      <span class="text-ink-gray-5 md:hidden"
                        >{{ __("Signed off on") }}:
                      </span>
                      {{
                        s.status === "Signed Off" && s.signed_on
                          ? dateFormat(s.signed_on, "D MMM YYYY")
                          : "—"
                      }}
                    </span>
                  </router-link>
                </li>
              </ul>
            </div>
          </template>
        </template>
      </div>
    </div>

    <SignoffFormDialog
      v-if="data?.can_create"
      v-model:open="showNew"
      :project-id="projectId"
      :uat="newUat"
      @saved="openSignoff"
    />
  </div>
</template>

<script setup lang="ts">
import StatTile from "@/components/StatTile.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { dateFormat } from "@/utils";
import { Button, TabButtons, createResource } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import { useRouter } from "vue-router";
import LucideBadgeCheck from "~icons/lucide/badge-check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleHelp from "~icons/lucide/circle-help";
import LucideClock from "~icons/lucide/clock";
import LucideClipboardCheck from "~icons/lucide/clipboard-check";
import LucideDownload from "~icons/lucide/download";
import LucideListChecks from "~icons/lucide/list-checks";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSend from "~icons/lucide/send";
import ProjectNav from "./components/ProjectNav.vue";
import SignoffFormDialog from "./components/SignoffFormDialog.vue";
import { SIGNOFF_STATUSES, signoffStatusMeta } from "./signoffMeta";
import { loadErrorMessage } from "./taskMeta";

interface SignoffRow {
  name: string;
  module_title: string;
  template?: string | null;
  /** Training, or UAT (the client's acceptance tests from the SRS) */
  signoff_type: "Training" | "UAT";
  status: string;
  /** the status in the customer's terms: Sent turns Viewed once they opened the link */
  customer_status: string;
  training_date?: string | null;
  trainer_name?: string | null;
  signatory_name?: string | null;
  signatory_email?: string | null;
  link_sent_on?: string | null;
  signed_on?: string | null;
  total: number;
  done: number;
  follow_up: number;
}

interface SignoffList {
  signoffs: SignoffRow[];
  signed: number;
  total: number;
  completion_letter: { file_name: string; file_url: string } | null;
  can_create: boolean;
  /** the project was made from an implementation plan: a UAT can be made from its SRS */
  can_create_uat: boolean;
}

const props = defineProps<{ projectId: string }>();
const router = useRouter();
const showNew = ref(false);
const newUat = ref(false);

function newSignoff(uat: boolean) {
  newUat.value = uat;
  showNew.value = true;
}

const signoffs = createResource({
  url: "helpdesk.api.project_signoff.get_project_signoffs",
  makeParams: () => ({ project: props.projectId }),
  auto: true,
  onError() {},
});

watch(
  () => props.projectId,
  () => signoffs.reload()
);

const data = computed(() => signoffs.data as SignoffList | undefined);
const hasUat = computed(
  () => !!data.value?.signoffs.some((s) => s.signoff_type === "UAT")
);
const waitingHeading = useId();
const listId = useId();
// a cancelled sign-off no longer counts
const counted = computed(() =>
  (data.value?.signoffs ?? []).filter((s) => s.status !== "Cancelled")
);
const signedCount = computed(
  () => counted.value.filter((s) => s.status === "Signed Off").length
);
const allSigned = computed(
  () => !!counted.value.length && signedCount.value === counted.value.length
);

const STATUS_TABS = ["All", ...SIGNOFF_STATUSES];
const statusFilter = ref("All");
function countFor(status: string) {
  const rows = data.value?.signoffs ?? [];
  return status === "All"
    ? rows.length
    : rows.filter((s) => s.status === status).length;
}
const shown = computed(() =>
  (data.value?.signoffs ?? []).filter(
    (s) => statusFilter.value === "All" || s.status === statusFilter.value
  )
);

/** What a sign-off not signed off yet waits for, and whether that is on us. */
function waitingFor(s: SignoffRow): { reason: string; onUs: boolean } {
  const who = s.signatory_name || __("the customer");
  if (s.status === "Draft") return { reason: __("Not sent yet"), onUs: true };
  if (s.status === "Changes Requested")
    return {
      reason: __("{0} asked for changes: edit it and send it again", who),
      onUs: true,
    };
  if (s.follow_up)
    return {
      reason:
        s.signoff_type === "UAT"
          ? __("{0} open issues for our team", String(s.follow_up))
          : __("{0} to clarify for our team", String(s.follow_up)),
      onUs: true,
    };
  if (s.customer_status === "Viewed")
    return {
      reason: __("With {0}: opened, waiting for their reply", who),
      onUs: false,
    };
  return { reason: __("With {0}: waiting for their reply", who), onUs: false };
}
// what is on us first, then what waits for the customer
const waiting = computed(() =>
  counted.value
    .filter((s) => s.status !== "Signed Off")
    .map((s) => ({
      name: s.name,
      title: s.module_title || s.template || s.name,
      ...waitingFor(s),
    }))
    .sort((a, b) => Number(b.onUs) - Number(a.onUs))
);
// items, not sign-offs: each one is a clarification someone has to give
const followUpCount = computed(
  () => data.value?.signoffs.reduce((sum, s) => sum + s.follow_up, 0) ?? 0
);
const withCustomerCount = computed(
  () => data.value?.signoffs.filter((s) => s.status === "Sent").length ?? 0
);

function openSignoff(name: string) {
  router.push({
    name: "TaskySignoff",
    params: { projectId: props.projectId, signoffId: name },
  });
}
</script>
