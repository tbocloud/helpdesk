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

    <div class="flex-1 overflow-auto">
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
              {{ __("Training sign-off") }}
            </h2>
            <div class="ml-auto">
              <Button
                v-if="data?.can_create && data.total"
                :label="__('New sign-off')"
                @click="showNew = true"
              >
                <template #prefix>
                  <LucidePlus class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </div>
          </div>

          <!-- roll-up -->
          <div
            v-if="!data || data.total"
            class="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3"
          >
            <StatTile
              compact
              :label="__('Signed')"
              :value="
                data
                  ? __('{0} of {1}', String(data.signed), String(data.total))
                  : ''
              "
              :icon="LucideCircleCheck"
              :icon-tone="allSigned ? 'success' : 'neutral'"
              :meter="data ? (data.signed / data.total) * 100 : null"
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
              :sub="__('Sent and not signed yet')"
              :icon="LucideSend"
              :loading="!data"
            />
          </div>

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
            v-else-if="!data.total"
            :icon="LucideClipboardCheck"
            :title="__('No sign-offs yet')"
            :message="
              data.can_create
                ? __(
                    'After each training, send the customer a checklist for that module. They confirm each item, ask about anything unclear, and sign off.'
                  )
                : __(
                    'Sign-offs for this project\'s trainings show up here once the project lead or manager creates them.'
                  )
            "
          >
            <Button
              v-if="data.can_create"
              variant="solid"
              :label="__('New sign-off')"
              @click="showNew = true"
            >
              <template #prefix>
                <LucidePlus class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </TaskyState>

          <ul
            v-else
            class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            role="list"
            :aria-label="__('Sign-offs')"
          >
            <li
              v-for="s in data.signoffs"
              :key="s.name"
              class="border-b border-outline-gray-1 last:border-b-0"
            >
              <router-link
                :to="{
                  name: 'TaskySignoff',
                  params: { projectId, signoffId: s.name },
                }"
                class="flex flex-col gap-2 px-4 py-3 transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4 md:flex-row md:items-center md:gap-4"
              >
                <div class="flex min-w-0 flex-1 flex-col gap-1">
                  <div class="flex min-w-0 flex-wrap items-center gap-2">
                    <span class="truncate text-base-medium text-ink-gray-9">{{
                      s.module_title
                    }}</span>
                    <TaskyBadge
                      :label="__(signoffStatusMeta(s.status).label)"
                      :tone="signoffStatusMeta(s.status).tone"
                      :icon="signoffStatusMeta(s.status).icon"
                    />
                  </div>
                  <div
                    class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-gray-6"
                  >
                    <span>{{ s.signatory_name }}</span>
                    <template v-if="s.trainer_name">
                      <span aria-hidden="true">·</span>
                      <span>{{ __("Trainer: {0}", s.trainer_name) }}</span>
                    </template>
                    <template v-if="s.training_date">
                      <span aria-hidden="true">·</span>
                      <span class="tabular-nums">{{
                        dateFormat(s.training_date, "D MMM YYYY")
                      }}</span>
                    </template>
                  </div>
                </div>
                <div
                  class="flex shrink-0 items-center gap-3 md:w-64 md:justify-end"
                >
                  <span
                    v-if="s.follow_up"
                    class="inline-flex items-center gap-1 text-xs font-medium text-warning"
                  >
                    <LucideCircleHelp class="size-3.5" aria-hidden="true" />
                    {{
                      s.follow_up === 1
                        ? __("1 to clarify")
                        : __("{0} to clarify", String(s.follow_up))
                    }}
                  </span>
                  <span class="flex items-center gap-2">
                    <span
                      class="block h-1.5 w-20 overflow-hidden rounded-full"
                      :class="
                        TRACK[s.status === 'Signed' ? 'success' : 'neutral']
                      "
                      aria-hidden="true"
                    >
                      <span
                        class="block h-full rounded-full"
                        :class="
                          FILL[s.status === 'Signed' ? 'success' : 'neutral']
                        "
                        :style="{
                          width: `${s.total ? (s.done / s.total) * 100 : 0}%`,
                        }"
                      />
                    </span>
                    <span
                      class="font-mono text-xs tabular-nums text-ink-gray-7"
                    >
                      {{ __("{0}/{1} done", String(s.done), String(s.total)) }}
                    </span>
                  </span>
                </div>
              </router-link>
            </li>
          </ul>
        </template>
      </div>
    </div>

    <SignoffFormDialog
      v-if="data?.can_create"
      v-model:open="showNew"
      :project-id="projectId"
      @saved="openSignoff"
    />
  </div>
</template>

<script setup lang="ts">
import StatTile from "@/components/StatTile.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { FILL, TRACK } from "@/components/tone";
import { __ } from "@/translation";
import { dateFormat } from "@/utils";
import { Button, createResource } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import LucideBadgeCheck from "~icons/lucide/badge-check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleHelp from "~icons/lucide/circle-help";
import LucideClipboardCheck from "~icons/lucide/clipboard-check";
import LucideDownload from "~icons/lucide/download";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSend from "~icons/lucide/send";
import ProjectNav from "./components/ProjectNav.vue";
import SignoffFormDialog from "./components/SignoffFormDialog.vue";
import { signoffStatusMeta } from "./signoffMeta";
import { loadErrorMessage } from "./taskMeta";

interface SignoffRow {
  name: string;
  module_title: string;
  status: string;
  training_date?: string | null;
  trainer_name?: string | null;
  signatory_name?: string | null;
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
}

const props = defineProps<{ projectId: string }>();
const router = useRouter();
const showNew = ref(false);

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
const allSigned = computed(
  () => !!data.value?.total && data.value.signed === data.value.total
);
// items, not sign-offs: each one is a clarification someone has to give
const followUpCount = computed(
  () => data.value?.signoffs.reduce((sum, s) => sum + s.follow_up, 0) ?? 0
);
const withCustomerCount = computed(
  () =>
    data.value?.signoffs.filter((s) => !["Draft", "Signed"].includes(s.status))
      .length ?? 0
);

function openSignoff(name: string) {
  router.push({
    name: "TaskySignoff",
    params: { projectId: props.projectId, signoffId: name },
  });
}
</script>
