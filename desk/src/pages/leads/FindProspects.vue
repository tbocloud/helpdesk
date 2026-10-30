<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <nav
          class="flex min-w-0 items-center gap-1.5 text-lg-medium"
          :aria-label="__('Breadcrumb')"
        >
          <router-link
            :to="{ name: 'Leads' }"
            class="shrink-0 rounded text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            >{{ __("Leads") }}</router-link
          >
          <LucideChevronRight
            class="size-4 shrink-0 text-ink-gray-4"
            aria-hidden="true"
          />
          <h1 class="truncate text-ink-gray-9">{{ __("Find prospects") }}</h1>
        </nav>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <div
          v-if="!options && leadOptions.loading"
          class="h-80 animate-pulse rounded-xl bg-surface-gray-2"
          aria-busy="true"
          :aria-label="__('Loading')"
        />

        <TaskyState
          v-else-if="!prospecting"
          :icon="LucideLock"
          :title="__('Find prospects isn\'t available to you')"
          :message="
            __(
              'It is for managers and department heads, and has to be switched on in TBO Smart Settings on the ERP site.'
            )
          "
        >
          <Button :label="__('Back to leads')" :route="{ name: 'Leads' }" />
        </TaskyState>

        <div
          v-else
          class="grid grid-cols-1 gap-4 lg:grid-cols-[26rem_1fr] lg:items-start"
        >
          <!-- the search: estimate first, start only after seeing the price -->
          <form
            class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
            novalidate
            @submit.prevent="onSubmit"
          >
            <h2 class="text-base-medium text-ink-gray-9">
              {{ __("Search") }}
            </h2>
            <FormControl
              v-model="form.industry"
              type="select"
              :label="__('Industry')"
              :options="choices(options?.industries, __('Choose an industry'))"
            />
            <FormControl
              v-if="options?.states?.length"
              v-model="form.state"
              type="select"
              :label="__('State')"
              :options="choices(options.states, __('Choose a state'))"
            />
            <FormControl
              v-else
              v-model="form.state"
              :label="__('State')"
              placeholder="Kerala"
            />
            <MultiSelect
              v-if="districtChoices.length"
              v-model="form.districts"
              :label="__('District(s)')"
              :placeholder="
                __('Choose up to {0}', String(prospecting.max_districts))
              "
              :options="districtChoices"
            />
            <FormControl
              v-else
              v-model="districtText"
              :label="__('District(s)')"
              :placeholder="__('Idukki, Malappuram')"
              :description="__('Separate districts with a comma.')"
            />
            <FormControl
              v-model="form.provider"
              type="select"
              :label="__('Provider')"
              :options="providerChoices"
            />
            <p
              v-if="provider"
              class="-mt-1 flex items-start gap-1.5 text-p-sm text-ink-gray-6"
            >
              <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              {{ provider.coverage }}
            </p>
            <div class="grid grid-cols-2 gap-3">
              <FormControl
                v-model.number="form.max_results"
                type="number"
                :label="__('Max results')"
                :min="1"
                :max="prospecting.max_results"
              />
              <FormControl
                v-model="form.department"
                type="select"
                :label="__('Department')"
                :options="departmentChoices"
              />
            </div>
            <label class="flex items-center gap-2 text-p-sm text-ink-gray-8">
              <Checkbox v-model="form.require_phone" />
              {{ __("Only businesses with a phone number") }}
            </label>

            <p v-if="problem" role="alert" class="text-p-sm text-danger">
              {{ problem }}
            </p>

            <!-- the price, then the one primary action: start -->
            <section
              v-if="estimated"
              class="flex flex-col gap-2 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3"
              :aria-label="__('Estimate')"
            >
              <dl class="grid grid-cols-2 gap-3">
                <div class="flex flex-col">
                  <dt class="text-xs text-ink-gray-5">{{ __("Cost") }}</dt>
                  <dd class="font-mono text-xl tabular-nums text-ink-gray-9">
                    {{ usd(estimated.estimated_cost) }}
                  </dd>
                </div>
                <div class="flex flex-col">
                  <dt class="text-xs text-ink-gray-5">
                    {{ __("Businesses") }}
                  </dt>
                  <dd class="font-mono text-xl tabular-nums text-ink-gray-9">
                    {{
                      estimated.estimated_cost
                        ? __("up to {0}", String(estimated.expected_count))
                        : estimated.expected_count
                    }}
                  </dd>
                </div>
              </dl>
              <p
                v-if="estimated.estimate_note"
                class="text-p-sm text-ink-gray-7"
              >
                {{ estimated.estimate_note }}
              </p>
              <p v-if="provider?.paid" class="text-p-sm text-ink-gray-6">
                {{
                  __(
                    "This month: {0} of {1}.",
                    usd(prospecting.month_spend),
                    usd(prospecting.monthly_cap)
                  )
                }}
              </p>
              <p class="text-xs text-ink-gray-5">
                {{ __("Change anything above to estimate again.") }}
              </p>
            </section>

            <div class="flex justify-end">
              <Button
                v-if="estimated"
                variant="solid"
                type="submit"
                :label="__('Start run')"
                :loading="start.loading"
              />
              <Button
                v-else
                variant="solid"
                type="submit"
                :label="__('Estimate')"
                :loading="estimate.loading"
                :disabled="!ready"
              />
            </div>
          </form>

          <!-- the runs, newest first; a running one updates by itself -->
          <section
            class="min-w-0 rounded-xl border border-outline-gray-2 bg-surface-base"
            :aria-label="__('Runs')"
          >
            <div
              class="flex items-center gap-2 border-b border-outline-gray-1 px-4 py-3"
            >
              <h2 class="text-base-medium text-ink-gray-9">{{ __("Runs") }}</h2>
              <Button
                class="ml-auto"
                variant="ghost"
                :loading="runs.loading && !!runList"
                :aria-label="__('Refresh')"
                @click="runs.reload()"
              >
                <template #icon>
                  <LucideRefreshCw class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </div>

            <div
              v-if="!runs.data && runs.loading"
              class="flex flex-col gap-2 p-4"
              aria-busy="true"
              :aria-label="__('Loading')"
            >
              <div class="h-14 animate-pulse rounded-lg bg-surface-gray-2" />
              <div class="h-14 animate-pulse rounded-lg bg-surface-gray-2" />
            </div>
            <TaskyState
              v-else-if="runs.error && !runs.data"
              error
              :icon="LucideCircleAlert"
              :title="__('Couldn\'t load the runs')"
              :message="
                errorText(
                  runs.error,
                  __('Check your connection and try again.')
                )
              "
            >
              <Button :label="__('Try again')" @click="runs.reload()" />
            </TaskyState>
            <TaskyState
              v-else-if="!runs.data?.available"
              :icon="LucideSearchX"
              :title="__('The ERP site can\'t find prospects yet')"
              :message="__('It needs the latest TBO Smart.')"
            />
            <TaskyState
              v-else-if="!runList.length"
              :icon="LucideSearch"
              :title="__('No runs yet')"
              :message="
                __(
                  'Pick an industry and districts, estimate, then start. The businesses land in the department\'s pool for the call batches.'
                )
              "
            />
            <ul v-else class="divide-y divide-outline-gray-1">
              <li v-for="run in runList" :key="run.name">
                <button
                  type="button"
                  class="flex w-full flex-col gap-1.5 px-4 py-3 text-left hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
                  @click="openRun = run.name"
                >
                  <span class="flex flex-wrap items-center gap-2">
                    <span class="min-w-0 truncate text-base text-ink-gray-9">{{
                      runTitle(run)
                    }}</span>
                    <TaskyBadge
                      class="ml-auto"
                      :label="STATUS[run.status].label"
                      :tone="STATUS[run.status].tone"
                      :icon="STATUS[run.status].icon"
                    />
                  </span>
                  <span
                    class="flex flex-wrap gap-x-4 gap-y-0.5 text-p-sm text-ink-gray-6"
                  >
                    <span>{{ run.provider }}</span>
                    <span>{{ run.department }}</span>
                    <span class="font-mono tabular-nums">{{
                      __(
                        "{0} found · {1} new · {2} duplicates",
                        String(run.count_found),
                        String(run.count_created),
                        String(run.count_duplicates)
                      )
                    }}</span>
                    <span class="font-mono tabular-nums">{{
                      usd(run.actual_cost || run.estimated_cost)
                    }}</span>
                    <time :datetime="run.creation">{{
                      dayjs(run.creation).format("D MMM, h:mm a")
                    }}</time>
                  </span>
                </button>
              </li>
            </ul>
          </section>
        </div>
      </div>
    </div>

    <ProspectRunDialog v-model:open="showRun" :name="openRun" />
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useIntervalFn } from "@vueuse/core";
import {
  Button,
  Checkbox,
  createResource,
  dayjs,
  FormControl,
  MultiSelect,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideInfo from "~icons/lucide/info";
import LucideLock from "~icons/lucide/lock";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSearch from "~icons/lucide/search";
import LucideSearchX from "~icons/lucide/search-x";
import ProspectRunDialog from "./ProspectRunDialog.vue";
import {
  choices,
  leadOptions,
  loadLeadOptions,
  usableDepartments,
  type LeadOptions,
} from "./leads";
import {
  runTitle,
  STATUS,
  usd,
  type ProspectRun,
  type ProspectValues,
} from "./prospects";

loadLeadOptions();
const options = computed(() => leadOptions.data as LeadOptions | undefined);
const prospecting = computed(() => options.value?.prospecting ?? null);

const form = reactive<
  Omit<ProspectValues, "require_phone"> & { require_phone: boolean }
>({
  industry: "",
  state: "Kerala",
  districts: [],
  provider: "",
  max_results: 50,
  department: "",
  require_phone: true,
});
const districtText = ref("");

// the first provider that works, and the department the settings or the person's own name
watch(
  prospecting,
  (p) => {
    if (!p) return;
    form.provider ||= p.providers.find((x) => x.available)?.key ?? "";
    form.max_results = Math.min(form.max_results, p.max_results);
    form.department ||=
      p.default_department ||
      usableDepartments(options.value).find((d) => d.is_head)?.name ||
      "";
  },
  { immediate: true }
);

const provider = computed(() =>
  prospecting.value?.providers.find((p) => p.key === form.provider)
);
const providerChoices = computed(() =>
  (prospecting.value?.providers ?? []).map((p) => ({
    label: p.available ? `${p.label}` : `${p.label} – ${__("not set up")}`,
    value: p.key,
    disabled: !p.available,
  }))
);
const departmentChoices = computed(() =>
  choices(
    usableDepartments(options.value).map((d) => d.name),
    __("Choose a department")
  )
);
const districtChoices = computed(() => {
  const o = options.value;
  const known = [
    ...(o?.districts_by_state?.[form.state] ?? []),
    ...(form.state === "Kerala" ? o?.kerala_districts ?? [] : []),
  ];
  return [...new Set(known)].sort().map((d) => ({ label: d, value: d }));
});

const districts = computed(() =>
  districtChoices.value.length
    ? form.districts
    : districtText.value
        .split(/[,\n]/)
        .map((d) => d.trim())
        .filter(Boolean)
);
const ready = computed(
  () =>
    !!form.industry &&
    !!form.state.trim() &&
    districts.value.length > 0 &&
    districts.value.length <= (prospecting.value?.max_districts ?? 10) &&
    !!provider.value?.available &&
    !!form.department &&
    form.max_results >= 1
);
const problem = ref("");

const estimated = ref<ProspectRun | null>(null);
// any change to the search makes the price stale
watch([form, districtText], () => (estimated.value = null), { deep: true });

const estimate = createResource({
  url: "helpdesk.api.prospects.estimate_prospect_run",
  onSuccess(run: ProspectRun) {
    problem.value = "";
    estimated.value = run;
  },
  onError(error: unknown) {
    problem.value = errorText(error, __("Couldn't estimate the run."));
  },
});
const start = createResource({
  url: "helpdesk.api.prospects.start_prospect_run",
  onSuccess(run: ProspectRun) {
    problem.value = "";
    estimated.value = null;
    toast.success(__("Started: {0}", runTitle(run)));
    runs.reload();
    openRun.value = run.name;
    showRun.value = true;
  },
  onError(error: unknown) {
    problem.value = errorText(error, __("Couldn't start the run."));
  },
});

function onSubmit() {
  problem.value = "";
  if (estimated.value) {
    start.submit({ name: estimated.value.name });
    return;
  }
  if (!ready.value) return;
  estimate.submit({
    values: {
      ...form,
      districts: districts.value,
      require_phone: form.require_phone ? 1 : 0,
    },
  });
}

const runs = createResource({
  url: "helpdesk.api.prospects.get_prospect_runs",
  auto: true,
});
const runList = computed(() => (runs.data?.runs ?? []) as ProspectRun[]);
const anyRunning = computed(() =>
  runList.value.some((r) => r.status === "Running")
);
const { pause, resume } = useIntervalFn(() => runs.reload(), 5000, {
  immediate: false,
});
watch(anyRunning, (busy) => (busy ? resume() : pause()), { immediate: true });

const showRun = ref(false);
const openRun = ref("");
watch(openRun, (name) => (showRun.value = !!name));
watch(showRun, (open) => {
  if (!open) {
    openRun.value = "";
    runs.reload();
  }
});
</script>
