<template>
  <div class="flex h-full flex-col">
    <ProjectNav :project-id="projectId" />

    <div class="flex-1 overflow-auto">
      <div
        class="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-5 md:px-6"
      >
        <TaskyState
          v-if="info.error && !loaded"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the commission')"
          :message="
            errorText(info.error, __('Check your connection and try again.'))
          "
        >
          <Button :label="__('Retry')" @click="load" />
        </TaskyState>

        <TaskyState
          v-else-if="info.data && !info.data.available"
          :icon="LucideCloudOff"
          :title="__('Commission isn\'t available yet')"
          :message="__('The ERP site needs the latest TBO Smart.')"
        />

        <div
          v-else-if="!loaded"
          class="h-40 animate-pulse rounded-xl bg-surface-gray-1"
          aria-busy="true"
          :aria-label="__('Loading')"
        />

        <template v-else>
          <div>
            <h2 class="text-lg-semibold text-ink-gray-9">
              {{ __("Commission") }}
            </h2>
            <p class="mt-1 max-w-prose text-p-sm text-ink-gray-6">
              {{
                __(
                  "Who earns commission on the money collected on this project, and by which plan. With no earners, the owner of the lead behind each payment earns all of it, by the plan that matches the rules in Settings → CRM."
                )
              }}
            </p>
          </div>

          <section class="grid grid-cols-2 gap-3" :aria-label="__('So far')">
            <StatTile
              compact
              :label="__('Collected so far')"
              :value="fullAmount(info.data.collected, currency)"
              :sub="__('{0} payments', String(info.data.payments))"
            />
            <StatTile
              compact
              :label="__('Commission so far')"
              :value="fullAmount(info.data.commission, currency)"
              :sub="__('In statements')"
            />
          </section>

          <form class="flex flex-col gap-4" novalidate @submit.prevent="save">
            <div class="flex flex-col gap-1.5">
              <div class="flex items-end gap-2">
                <FormControl
                  v-model="key"
                  class="flex-1"
                  :label="__('Project name on the invoices')"
                  autocomplete="off"
                  :disabled="!!info.data.setup"
                />
                <Button
                  v-if="!info.data.setup"
                  :label="__('Look up')"
                  :disabled="!key.trim()"
                  @click="load"
                />
              </div>
              <p class="text-p-xs text-ink-gray-6">
                {{
                  __(
                    "Payments are matched to the project named on their Sales Order or Invoice, else to this project when it is linked on the lead's documents. If the invoices use another name, type it here."
                  )
                }}
              </p>
            </div>

            <fieldset class="flex flex-col gap-2">
              <legend class="text-sm text-ink-gray-7">
                {{ __("Who earns") }}
              </legend>
              <div
                v-for="(earner, i) in form.earners"
                :key="i"
                role="group"
                :aria-label="__('Earner {0}', String(i + 1))"
                class="grid grid-cols-[1fr_6rem_auto] items-end gap-2"
              >
                <FormControl
                  v-model="earner.user"
                  type="select"
                  :options="userOptions"
                  :label="i === 0 ? __('Person') : undefined"
                  :aria-label="__('Earner {0}', String(i + 1))"
                />
                <FormControl
                  v-model="earner.share_percent"
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  :label="i === 0 ? __('Share %') : undefined"
                  :aria-label="__('Earner {0} share', String(i + 1))"
                />
                <Button
                  variant="ghost"
                  :label="__('Remove earner {0}', String(i + 1))"
                  @click="form.earners.splice(i, 1)"
                >
                  <template #icon>
                    <LucideTrash2 class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </div>
              <div class="flex flex-wrap items-center gap-3">
                <Button :label="__('Add earner')" @click="addEarner">
                  <template #prefix>
                    <LucidePlus class="size-4" aria-hidden="true" />
                  </template>
                </Button>
                <span
                  v-if="form.earners.length"
                  class="font-mono text-sm tabular-nums"
                  :class="total === 100 ? 'text-ink-gray-7' : 'text-danger'"
                  role="status"
                >
                  {{ __("Total {0}%", String(total)) }}
                </span>
              </div>
            </fieldset>

            <div class="flex flex-col gap-1.5">
              <FormControl
                v-model="form.plan"
                type="select"
                :label="__('Plan')"
                :options="planOptions"
                :disabled="form.use_override"
              />
              <p class="text-p-xs text-ink-gray-6">
                {{
                  form.use_override
                    ? __("This project uses its own slabs, below.")
                    : __("Match by rules picks the plan whose conditions fit.")
                }}
              </p>
            </div>

            <Switch
              v-model="form.use_override"
              :label="__('Use this project\'s own slabs instead of a plan')"
            />
            <template v-if="form.use_override">
              <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <FormControl
                  v-model="form.override_target"
                  type="number"
                  min="0"
                  :label="__('Monthly target')"
                />
                <FormControl
                  v-model="form.override_above_target_rate"
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  :label="__('Above-target rate (%)')"
                />
              </div>
              <CommissionSlabs v-model="form.override_slabs" />
            </template>

            <Switch v-model="form.is_active" :label="__('Active')" />

            <div
              v-if="problem"
              role="alert"
              class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
            >
              <LucideCircleAlert
                class="mt-0.5 size-4 shrink-0"
                aria-hidden="true"
              />
              <span>{{ problem }}</span>
            </div>
            <div>
              <Button
                variant="solid"
                type="submit"
                :label="__('Save')"
                :loading="saving"
              />
            </div>
          </form>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import CommissionSlabs from "@/components/Settings/CRM/CommissionSlabs.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { fullAmount } from "@/pages/leads/business/businessFormat";
import {
  schemeProblem,
  slabRows,
  type CommissionPlan,
  type ProjectCommissionSetup,
  type SlabForm,
} from "@/pages/leads/commission";
import { useAgentStore } from "@/stores/agent";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  createResource,
  FormControl,
  Switch,
  toast,
} from "frappe-ui";
import { computed, onMounted, reactive, ref } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCloudOff from "~icons/lucide/cloud-off";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
import ProjectNav from "./components/ProjectNav.vue";

const props = defineProps<{ projectId: string }>();
const { agents } = useAgentStore();

const key = ref(props.projectId);
const loaded = ref(false);
const saving = ref(false);
const problem = ref("");

interface Earner {
  user: string;
  share_percent: number | string;
}
const form = reactive({
  is_active: true,
  earners: [] as Earner[],
  plan: "",
  use_override: false,
  override_target: 0 as number | string,
  override_above_target_rate: 0 as number | string,
  override_slabs: [] as SlabForm[],
});

const info = createResource({
  url: "helpdesk.api.commission.get_project_commission",
  onSuccess(data: {
    available: boolean;
    setup: ProjectCommissionSetup | null;
  }) {
    if (!data.available) return;
    fill(data.setup);
    loaded.value = true;
  },
});
const plans = createResource({
  url: "helpdesk.api.commission.get_commission_plans",
  auto: true,
});
const currency = computed(() => info.data?.currency || "INR");

function load() {
  problem.value = "";
  info.submit({ project: key.value.trim() });
}

function fill(setup: ProjectCommissionSetup | null) {
  Object.assign(form, {
    is_active: setup ? !!setup.is_active : true,
    earners: (setup?.earners ?? []).map((e) => ({ ...e })),
    plan: setup?.plan ?? "",
    use_override: !!setup?.use_override,
    override_target: setup?.override_target ?? 0,
    override_above_target_rate: setup?.override_above_target_rate ?? 0,
    override_slabs: (setup?.override_slabs ?? []).map((s) => ({
      from_amount: s.from_amount,
      to_amount: s.to_amount ?? "",
      rate: s.rate,
    })),
  });
  if (setup) key.value = setup.project;
}

onMounted(() => {
  load();
  if (!agents.loading && !agents.data?.length && !agents.list.promise)
    agents.fetch();
});

const planOptions = computed(() => [
  { label: __("Match by rules"), value: "" },
  ...((plans.data?.plans ?? []) as CommissionPlan[]).map((p) => ({
    label: p.plan_name,
    value: p.name,
  })),
]);
const userOptions = computed(() => {
  const options = new Map<string, { label: string; value: string }>();
  for (const a of agents.data ?? [])
    if (a.user)
      options.set(a.user, {
        label: a.agent_name ? `${a.agent_name} (${a.user})` : a.user,
        value: a.user,
      });
  for (const e of form.earners)
    if (e.user && !options.has(e.user))
      options.set(e.user, { label: e.user, value: e.user });
  return [{ label: __("Pick a person"), value: "" }, ...options.values()];
});

const total = computed(
  () =>
    Math.round(
      form.earners.reduce((sum, e) => sum + (Number(e.share_percent) || 0), 0) *
        100
    ) / 100
);

function addEarner() {
  const left = Math.max(100 - total.value, 0);
  form.earners.push({
    user: "",
    share_percent: form.earners.length ? left : 100,
  });
}

function save() {
  if (saving.value) return;
  problem.value = "";
  if (!key.value.trim()) {
    problem.value = __("Name the project.");
    return;
  }
  if (form.earners.some((e) => !e.user)) {
    problem.value = __("Pick a person for every earner.");
    return;
  }
  if (form.earners.length && total.value !== 100) {
    problem.value = __("The shares must add up to 100%.");
    return;
  }
  const slabs = slabRows(form.override_slabs);
  if (form.use_override) {
    problem.value =
      schemeProblem(slabs, Number(form.override_above_target_rate) || 0) ||
      (slabs.length ? "" : __("Add at least one slab."));
    if (problem.value) return;
  }
  saving.value = true;
  call("helpdesk.api.commission.save_project_commission", {
    values: {
      project: key.value.trim(),
      is_active: form.is_active ? 1 : 0,
      earners: form.earners.map((e) => ({
        user: e.user,
        share_percent: Number(e.share_percent),
      })),
      plan: form.use_override ? "" : form.plan,
      use_override: form.use_override ? 1 : 0,
      override_target: Number(form.override_target) || 0,
      override_above_target_rate: Number(form.override_above_target_rate) || 0,
      override_slabs: slabs,
    },
  })
    .then((data) => {
      info.setData({ ...data, available: true });
      fill(data.setup);
      toast.success(__("Commission saved"));
    })
    // the ERP site's own reason, e.g. only a manager may
    .catch((e: unknown) => {
      problem.value = errorText(e, __("Couldn't save. Check your connection."));
    })
    .finally(() => (saving.value = false));
}
</script>
