<template>
  <!-- stays out until the ERP site's TBO Smart has commission -->
  <SettingsSection
    v-if="available || error"
    :title="__('Commission plans')"
    :description="
      __(
        'Commission is a percentage of the money collected on a project, in slabs: each slab\'s rate applies only to the part of the collection inside it. Money above the target earns the above-target rate where that is higher. A plan applies when its conditions match; the one matching the most wins (person, then project type, lead type, department). Set who earns on a project on its Commission tab.'
      )
    "
  >
    <template #actions>
      <Button
        v-if="available"
        :label="__('Add plan')"
        @click="openDialog(null)"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>

    <div
      v-if="error"
      role="alert"
      class="flex flex-wrap items-center gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
    >
      <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
      <span class="min-w-0 flex-1">{{ error }}</span>
      <Button :label="__('Try again')" @click="plans.reload()" />
    </div>
    <div
      v-else-if="!list.length"
      class="rounded-lg border border-dashed border-outline-gray-3 px-4 py-6 text-center text-p-sm text-ink-gray-6"
    >
      {{
        __(
          "No plans yet. Add one with no conditions as the default for everyone; money earns nothing until a plan applies."
        )
      }}
    </div>
    <ul
      v-else
      role="list"
      class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2"
      :aria-busy="plans.loading"
    >
      <li
        v-for="plan in list"
        :key="plan.name"
        class="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3"
      >
        <div class="flex min-w-0 flex-1 flex-col gap-0.5">
          <span class="truncate text-base-medium text-ink-gray-9">{{
            plan.plan_name
          }}</span>
          <span class="text-p-xs text-ink-gray-6">
            {{ conditionsText(plan) }} · {{ plan.basis }} ·
            <span class="tabular-nums">{{
              __("{0} slabs", String(plan.slabs.length))
            }}</span>
            <template v-if="plan.monthly_target > 0">
              ·
              <span class="font-mono tabular-nums">{{
                __("target {0}", fullAmount(plan.monthly_target, currency))
              }}</span>
            </template>
          </span>
        </div>
        <span v-if="!plan.is_active" class="text-p-xs text-ink-gray-5">{{
          __("Inactive")
        }}</span>
        <Button
          variant="ghost"
          :label="__('Edit {0}', plan.plan_name)"
          @click="openDialog(plan)"
        >
          <template #icon>
            <LucidePencil class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </li>
    </ul>
    <div
      v-if="plans.loading && !plans.data"
      class="h-12 animate-pulse rounded-lg bg-surface-gray-2"
      aria-busy="true"
      :aria-label="__('Loading')"
    />
  </SettingsSection>

  <Dialog
    v-model:open="showDialog"
    :title="editing ? __('Edit plan') : __('Add plan')"
    size="3xl"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="save"
    >
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl
          v-model="form.plan_name"
          :label="__('Name')"
          :disabled="!!editing"
          maxlength="140"
          required
          autocomplete="off"
        />
        <div class="flex flex-col gap-1.5">
          <FormControl
            v-model="form.basis"
            type="select"
            :label="__('Basis')"
            :options="BASIS_OPTIONS"
          />
          <p class="text-p-xs text-ink-gray-6">
            {{
              form.basis === "Project collected"
                ? __(
                    "Each project's money runs through the slabs on its own, and the target is per project."
                  )
                : __(
                    "Everything a person collects in the month runs through the slabs once, and the target is per person."
                  )
            }}
          </p>
        </div>
      </div>

      <fieldset class="flex flex-col gap-3">
        <legend class="text-sm text-ink-gray-7">
          {{ __("Applies when (leave blank to ignore)") }}
        </legend>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormControl
            v-model="form.department"
            type="select"
            :label="__('Department')"
            :options="departmentOptions"
          />
          <FormControl
            v-model="form.lead_type"
            type="select"
            :label="__('Lead type')"
            :options="leadTypeOptions"
          />
          <FormControl
            v-model="form.project_type"
            :label="__('Project type')"
            autocomplete="off"
          />
          <FormControl
            v-model="form.user"
            type="select"
            :label="__('Person')"
            :options="userOptions"
          />
        </div>
      </fieldset>

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl
          v-model="form.monthly_target"
          type="number"
          min="0"
          :label="__('Monthly target')"
        />
        <FormControl
          v-model="form.above_target_rate"
          type="number"
          min="0"
          max="100"
          step="0.1"
          :label="__('Above-target rate (%)')"
        />
      </div>

      <CommissionSlabs v-model="form.slabs" />

      <section
        class="flex flex-col gap-2 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3"
        :aria-label="__('Example')"
      >
        <div class="flex flex-wrap items-end gap-3">
          <FormControl
            v-model="example"
            type="number"
            min="0"
            class="w-44"
            :label="__('Example: collected')"
          />
          <p
            class="pb-1 text-base-medium text-ink-gray-9"
            role="status"
            aria-live="polite"
          >
            <template v-if="exampleProblem">{{ exampleProblem }}</template>
            <template v-else>{{
              __(
                "On {0} collected: {1}",
                fullAmount(Number(example) || 0, currency),
                fullAmount(preview.total, currency)
              )
            }}</template>
          </p>
        </div>
        <ul
          v-if="!exampleProblem && preview.pieces.length"
          role="list"
          class="flex flex-col gap-0.5"
        >
          <li
            v-for="(piece, i) in preview.pieces"
            :key="i"
            class="flex justify-between gap-3 text-p-xs text-ink-gray-7"
          >
            <span class="font-mono tabular-nums">
              {{
                __(
                  "{0} to {1} at {2}%",
                  shortAmount(piece.from, currency),
                  shortAmount(piece.to, currency),
                  String(piece.rate)
                )
              }}
              <template v-if="piece.above">
                ({{ __("above target") }})</template
              >
            </span>
            <span class="font-mono tabular-nums">{{
              fullAmount(piece.commission, currency)
            }}</span>
          </li>
        </ul>
      </section>

      <Switch v-model="form.is_active" :label="__('Active')" />
      <div
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ errorMessage }}</span>
      </div>
    </form>
    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="editing ? __('Save changes') : __('Add plan')"
          :loading="saving"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { fullAmount, shortAmount } from "@/pages/leads/business/businessFormat";
import {
  previewCommission,
  schemeProblem,
  slabRows,
  type SlabForm,
  type CommissionBasis,
  type CommissionPlan,
} from "@/pages/leads/commission";
import { useAgentStore } from "@/stores/agent";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  createResource,
  Dialog,
  FormControl,
  Switch,
  toast,
} from "frappe-ui";
import { computed, onMounted, reactive, ref, useId } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlus from "~icons/lucide/plus";
import SettingsSection from "../SettingsSection.vue";
import CommissionSlabs from "./CommissionSlabs.vue";

const { agents } = useAgentStore();
const formId = `commission-plan-${useId()}`;

const plans = createResource({
  url: "helpdesk.api.commission.get_commission_plans",
});
const available = computed(() => !!plans.data?.available);
const list = computed(() => (plans.data?.plans ?? []) as CommissionPlan[]);
const currency = computed(() => plans.data?.currency || "INR");
const error = computed(() =>
  plans.error
    ? errorText(
        plans.error,
        __("Couldn't load the commission plans. Check your connection.")
      )
    : ""
);

onMounted(() => {
  plans.fetch();
  if (!agents.loading && !agents.data?.length && !agents.list.promise)
    agents.fetch();
});

const BASIS_OPTIONS = [
  { label: __("Project collected"), value: "Project collected" },
  { label: __("Collected (all)"), value: "Collected (all)" },
];
const none = { label: __("Anyone"), value: "" };
const departmentOptions = computed(() => [
  none,
  ...((plans.data?.departments ?? []) as string[]).map((d) => ({
    label: d,
    value: d,
  })),
]);
const leadTypeOptions = computed(() => [
  { label: __("Any type"), value: "" },
  ...((plans.data?.lead_types ?? []) as string[]).map((t) => ({
    label: t,
    value: t,
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
  for (const p of list.value)
    if (p.user && !options.has(p.user))
      options.set(p.user, { label: p.user, value: p.user });
  return [{ label: __("Anyone"), value: "" }, ...options.values()];
});

function conditionsText(plan: CommissionPlan) {
  const parts = [
    plan.user,
    plan.project_type,
    plan.lead_type,
    plan.department,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : __("Applies to everyone");
}

interface PlanForm {
  plan_name: string;
  is_active: boolean;
  basis: CommissionBasis;
  department: string;
  lead_type: string;
  project_type: string;
  user: string;
  monthly_target: number | string;
  above_target_rate: number | string;
  slabs: SlabForm[];
}

const showDialog = ref(false);
const editing = ref<CommissionPlan | null>(null);
const errorMessage = ref("");
const saving = ref(false);
const example = ref<number | string>(300000);
const form = reactive<PlanForm>(blank());

function blank(): PlanForm {
  return {
    plan_name: "",
    is_active: true,
    basis: "Project collected",
    department: "",
    lead_type: "",
    project_type: "",
    user: "",
    monthly_target: 0,
    above_target_rate: 0,
    slabs: [{ from_amount: 0, to_amount: "", rate: "" }],
  };
}

function openDialog(plan: CommissionPlan | null) {
  editing.value = plan;
  errorMessage.value = "";
  Object.assign(
    form,
    plan
      ? {
          plan_name: plan.plan_name,
          is_active: !!plan.is_active,
          basis: plan.basis,
          department: plan.department ?? "",
          lead_type: plan.lead_type ?? "",
          project_type: plan.project_type ?? "",
          user: plan.user ?? "",
          monthly_target: plan.monthly_target,
          above_target_rate: plan.above_target_rate,
          slabs: plan.slabs.map((s) => ({
            from_amount: s.from_amount,
            to_amount: s.to_amount ?? "",
            rate: s.rate,
          })),
        }
      : blank()
  );
  showDialog.value = true;
}

const cleanSlabs = computed(() => slabRows(form.slabs));
const exampleProblem = computed(() =>
  schemeProblem(cleanSlabs.value, Number(form.above_target_rate) || 0)
);
const preview = computed(() =>
  previewCommission(
    Number(example.value) || 0,
    Number(form.monthly_target) || 0,
    cleanSlabs.value,
    Number(form.above_target_rate) || 0
  )
);

function save() {
  if (saving.value) return;
  if (!form.plan_name.trim()) {
    errorMessage.value = __("Give the plan a name.");
    return;
  }
  if (!cleanSlabs.value.length) {
    errorMessage.value = __("Add at least one slab.");
    return;
  }
  if (exampleProblem.value) {
    errorMessage.value = exampleProblem.value;
    return;
  }
  errorMessage.value = "";
  saving.value = true;
  call("helpdesk.api.commission.save_commission_plan", {
    name: editing.value?.name ?? null,
    values: {
      plan_name: form.plan_name.trim(),
      is_active: form.is_active ? 1 : 0,
      basis: form.basis,
      department: form.department,
      lead_type: form.lead_type,
      project_type: form.project_type.trim(),
      user: form.user,
      monthly_target: Number(form.monthly_target) || 0,
      above_target_rate: Number(form.above_target_rate) || 0,
      slabs: cleanSlabs.value,
    },
  })
    .then(() => {
      toast.success(editing.value ? __("Plan saved") : __("Plan added"));
      showDialog.value = false;
      plans.reload();
    })
    // the ERP site's own reason, e.g. two plans with the same conditions
    .catch((e: unknown) => {
      errorMessage.value = errorText(
        e,
        __("Couldn't save the plan. Check your connection and try again.")
      );
    })
    .finally(() => (saving.value = false));
}
</script>
