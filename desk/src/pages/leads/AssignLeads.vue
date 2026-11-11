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
          <h1 class="truncate text-ink-gray-9">{{ __("Assign leads") }}</h1>
        </nav>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-y-auto overflow-x-hidden">
      <div
        class="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-5 md:px-6"
      >
        <TaskyState
          v-if="plans.error && !plans.data"
          :error="!isRefusal"
          :icon="isRefusal ? LucideLock : LucideCircleAlert"
          :title="
            isRefusal
              ? __('Assign leads isn\'t available to you')
              : __('Couldn\'t load the plans')
          "
          :message="
            errorText(plans.error, __('Check your connection and try again.'))
          "
        >
          <Button
            v-if="!isRefusal"
            :label="__('Try again')"
            @click="plans.reload()"
          />
          <Button
            v-else
            :label="__('Back to leads')"
            :route="{ name: 'Leads' }"
          />
        </TaskyState>

        <div
          v-else-if="!plans.data"
          class="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_22rem]"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div class="h-96 animate-pulse rounded-xl bg-surface-gray-2" />
          <div class="h-80 animate-pulse rounded-xl bg-surface-gray-2" />
        </div>

        <TaskyState
          v-else-if="!plans.data.available"
          :icon="LucideCloudOff"
          :title="__('The ERP site can\'t assign leads yet')"
          :message="
            __('It needs the latest TBO Smart. Ask an admin to update it.')
          "
        />

        <TaskyState
          v-else-if="!plans.data.departments.length"
          :icon="LucidePhoneOff"
          :title="__('No department hands out daily calls')"
          :message="
            __(
              'Turn on daily call batches for a department in Settings, CRM, Lead departments. Then plan its people here.'
            )
          "
        />

        <template v-else-if="current">
          <!-- the department first: the people and products below are its own -->
          <FormControl
            :model-value="current.department"
            type="select"
            class="w-full sm:w-72"
            :label="__('Department')"
            :options="departmentOptions"
            :description="
              industryMode
                ? __(
                    '{0} people, no products: leads are given by industry',
                    String(current.members.length)
                  )
                : __(
                    '{0} people, {1} products',
                    String(current.members.length),
                    String(current.products.length)
                  )
            "
            @update:model-value="pickDepartment(String($event))"
          />

          <div
            v-if="stuck"
            class="flex flex-wrap items-center gap-3 rounded-lg border border-outline-gray-2 bg-warning-soft px-4 py-3"
            role="alert"
          >
            <LucideTriangleAlert
              class="size-4 shrink-0 text-warning"
              aria-hidden="true"
            />
            <p class="min-w-0 flex-1 text-sm text-ink-gray-9">
              {{
                stuck === "zero"
                  ? __(
                      "No one in {0} gets calls from the pool: everyone's plan is 0. {1} leads are waiting.",
                      current.department,
                      String(leadsReady(current, null))
                    )
                  : __(
                      "{0} doesn't hand out pool leads, so the {1} unassigned leads wait. Turn it on in Settings, CRM, Lead departments.",
                      current.department,
                      String(leadsReady(current, null))
                    )
              }}
            </p>
            <Button
              v-if="stuck === 'zero'"
              :label="__('Set the plan')"
              @click="pickAll(true)"
            />
          </div>

          <div
            class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start"
          >
            <!-- the people and what each is handed now -->
            <section
              class="min-w-0 rounded-xl border border-outline-gray-2 bg-surface-base"
              :aria-labelledby="peopleHeading"
            >
              <div
                class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3"
              >
                <Checkbox
                  v-if="current.members.length"
                  :model-value="allPicked"
                  :aria-label="__('Pick everyone')"
                  @update:model-value="pickAll(!!$event)"
                />
                <h2
                  :id="peopleHeading"
                  class="flex-1 text-base-medium text-ink-gray-9"
                >
                  {{ __("People") }}
                </h2>
                <span class="text-sm text-ink-gray-6 tabular-nums">
                  {{
                    picked.length
                      ? __("{0} picked", String(picked.length))
                      : __("{0} people", String(current.members.length))
                  }}
                </span>
                <Button
                  :label="__('Unassigned leads')"
                  @click="openLeads(null)"
                />
              </div>

              <TaskyState
                v-if="!current.members.length"
                :icon="LucideUsers"
                :title="__('{0} has no members', current.department)"
                :message="
                  __(
                    'Add the people who call for it in Settings, CRM, Lead departments.'
                  )
                "
              />

              <template v-else>
                <div
                  class="hidden grid-cols-[2rem_minmax(0,1fr)_9rem_repeat(var(--slots),4.5rem)_6rem_6rem] items-center gap-2 px-4 py-2 text-xs text-ink-gray-6 md:grid"
                  :style="{ '--slots': current.slots.length }"
                  aria-hidden="true"
                >
                  <span />
                  <span>{{ __("Name") }}</span>
                  <span>{{
                    industryMode ? __("Industry") : __("Product")
                  }}</span>
                  <span
                    v-for="slot in current.slots"
                    :key="slot.label"
                    class="text-right"
                    >{{ slot.label }}</span
                  >
                  <span class="text-right">{{ __("Today") }}</span>
                  <span class="text-right">{{ __("Leads") }}</span>
                </div>
                <ul
                  class="divide-y divide-outline-gray-1 border-t border-outline-gray-1 md:border-t-0"
                >
                  <li v-for="member in current.members" :key="member.user">
                    <label
                      class="grid cursor-pointer grid-cols-[2rem_minmax(0,1fr)] items-center gap-x-2 gap-y-1 px-4 py-3 hover:bg-surface-gray-1 md:grid-cols-[2rem_minmax(0,1fr)_9rem_repeat(var(--slots),4.5rem)_6rem_6rem]"
                      :class="isPicked(member.user) && 'bg-surface-gray-1'"
                      :style="{ '--slots': current.slots.length }"
                    >
                      <Checkbox
                        :model-value="isPicked(member.user)"
                        :aria-label="member.full_name"
                        @update:model-value="toggle(member.user, !!$event)"
                      />
                      <span class="min-w-0">
                        <span class="block truncate text-base text-ink-gray-9">
                          {{ member.full_name }}
                        </span>
                        <!-- on a phone the plan is one line under the name -->
                        <span
                          class="block truncate text-sm text-ink-gray-6 md:hidden"
                        >
                          {{ planLine(member) }}
                        </span>
                      </span>
                      <span
                        class="col-start-2 hidden min-w-0 truncate text-sm md:col-start-auto md:block"
                        :class="
                          planChoice(member)
                            ? 'text-ink-gray-8'
                            : 'text-ink-gray-5'
                        "
                      >
                        {{ planChoice(member) || anyLabel }}
                      </span>
                      <span
                        v-for="slot in current.slots"
                        :key="slot.label"
                        class="hidden text-right font-mono text-sm tabular-nums md:block"
                        :class="
                          member.has_plan
                            ? 'text-ink-gray-9'
                            : 'text-ink-gray-5'
                        "
                      >
                        {{ member.sizes[slot.label] ?? slot.size }}
                      </span>
                      <span
                        class="col-start-2 text-sm text-ink-gray-6 tabular-nums md:col-start-auto md:text-right"
                        :title="__('Called / handed today')"
                      >
                        <span class="font-mono">{{
                          `${member.today.called}/${member.today.size}`
                        }}</span>
                        <span class="md:hidden"> {{ __("called today") }}</span>
                      </span>
                      <!-- a button inside the row's label: it must not tick the person -->
                      <button
                        type="button"
                        class="col-start-2 justify-self-start rounded px-1 text-sm text-ink-gray-8 underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight md:col-start-auto md:justify-self-end"
                        :aria-label="
                          __('See and move the leads of {0}', member.full_name)
                        "
                        @click.prevent.stop="openLeads(member)"
                      >
                        <span class="font-mono tabular-nums">{{
                          member.leads
                        }}</span>
                        {{ __("leads") }}
                      </button>
                    </label>
                  </li>
                </ul>
                <p
                  class="border-t border-outline-gray-1 px-4 py-2 text-xs text-ink-gray-5"
                >
                  {{
                    __(
                      "Gray numbers are the department's slot sizes: that person has no plan of their own."
                    )
                  }}
                </p>
              </template>
            </section>

            <!-- the plan for the people picked -->
            <form
              class="flex flex-col gap-4 rounded-xl border border-outline-gray-2 bg-surface-base p-4 lg:sticky lg:top-0"
              novalidate
              :aria-labelledby="planHeading"
              @submit.prevent="assign"
            >
              <div>
                <h2 :id="planHeading" class="text-base-medium text-ink-gray-9">
                  {{
                    picked.length
                      ? __("Assign to {0}", pickedLabel)
                      : __("Assign leads")
                  }}
                </h2>
                <p v-if="!picked.length" class="mt-1 text-p-sm text-ink-gray-6">
                  {{
                    __("Pick people on the list, then choose what they call.")
                  }}
                </p>
              </div>

              <FormControl
                v-if="industryMode"
                v-model="form.industry"
                type="select"
                :label="__('Industry')"
                :disabled="!picked.length"
                :options="industryOptions"
              />
              <FormControl
                v-else
                v-model="form.product"
                type="select"
                :label="__('Product')"
                :disabled="!picked.length || !!current.campaign_product"
                :options="productOptions"
                :description="
                  current.campaign_product
                    ? __(
                        '{0} calls only for {1}, set in the department.',
                        current.department,
                        current.campaign_product
                      )
                    : undefined
                "
              />

              <!-- the product's unassigned leads: see them, or hand some out now -->
              <div
                v-if="picked.length"
                class="flex flex-col gap-2 rounded-lg border border-outline-gray-2 p-3"
              >
                <div class="flex items-center justify-between gap-2">
                  <p class="text-p-sm text-ink-gray-8">
                    <span class="font-mono tabular-nums">{{ ready }}</span>
                    {{
                      chosen
                        ? __("unassigned {0} leads", chosen)
                        : __("unassigned leads")
                    }}
                  </p>
                  <Button
                    :label="__('See leads')"
                    :disabled="!ready"
                    @click="openPool"
                  />
                </div>
                <div v-if="ready" class="flex items-end gap-2">
                  <FormControl
                    v-model="giveCount"
                    type="number"
                    min="1"
                    :max="MAX_GIVE"
                    inputmode="numeric"
                    class="w-28"
                    :label="
                      picked.length === 1 ? __('Give now') : __('Give each now')
                    "
                  />
                  <Button
                    :label="__('Give to {0}', pickedLabel)"
                    :loading="giving"
                    :disabled="giving"
                    @click="giveNow"
                  />
                </div>
                <p class="text-xs text-ink-gray-5">
                  {{
                    __(
                      "Given now: they own the leads at once, and their next batch can call them. The plan below sets how many calls a day."
                    )
                  }}
                </p>
              </div>

              <fieldset class="flex flex-col gap-2" :disabled="!picked.length">
                <legend class="mb-1.5 text-xs text-ink-gray-5">
                  {{ __("Calls per person") }}
                </legend>
                <div class="grid grid-cols-2 gap-3">
                  <FormControl
                    v-for="slot in current.slots"
                    :key="slot.label"
                    v-model="form.sizes[slot.label]"
                    type="number"
                    min="0"
                    :max="MAX_CALLS"
                    inputmode="numeric"
                    :label="slot.label"
                    :description="`${slot.start_time}–${slot.end_time}`"
                  />
                </div>
              </fieldset>

              <div
                v-if="picked.length"
                class="flex flex-col gap-1.5 rounded-lg bg-surface-gray-1 px-3 py-2.5 text-sm"
                aria-live="polite"
              >
                <p class="text-ink-gray-8">
                  {{
                    __(
                      "{0} calls a day each, {1} together.",
                      String(perPerson),
                      String(perPerson * picked.length)
                    )
                  }}
                </p>
                <p
                  v-if="current.pull_unassigned"
                  class="flex items-start gap-1.5"
                  :class="short ? 'text-ink-gray-8' : 'text-ink-gray-6'"
                >
                  <LucideTriangleAlert
                    v-if="short"
                    class="mt-0.5 size-4 shrink-0 text-warning"
                    aria-hidden="true"
                  />
                  <span>
                    {{
                      __(
                        "{0} unassigned {1} leads are ready.",
                        String(ready),
                        chosen || __("open")
                      )
                    }}
                    <template v-if="short">
                      {{
                        __(
                          "Not enough for a full day: each batch starts with the person's own leads, then takes what is left."
                        )
                      }}
                    </template>
                  </span>
                </p>
                <p v-else class="text-ink-gray-6">
                  {{
                    __(
                      "This department doesn't hand out unassigned leads, so each person calls their own."
                    )
                  }}
                </p>
                <p
                  v-if="autoAssignText(current)"
                  class="flex items-start gap-1.5 text-ink-gray-6"
                >
                  <LucideClock
                    class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
                    aria-hidden="true"
                  />
                  <span>{{ autoAssignText(current) }}</span>
                </p>
              </div>

              <ErrorMessage
                v-if="formError"
                :message="formError"
                role="alert"
              />

              <div class="flex flex-col gap-2">
                <Button
                  type="submit"
                  variant="solid"
                  size="md"
                  :label="__('Assign leads')"
                  :loading="save.loading && !clearing"
                  :disabled="!picked.length || save.loading"
                />
                <Button
                  v-if="pickedWithPlan.length"
                  variant="ghost"
                  :label="
                    __(
                      'Back to department sizes ({0})',
                      String(pickedWithPlan.length)
                    )
                  "
                  :loading="save.loading && clearing"
                  :disabled="save.loading"
                  @click="clearPlans"
                />
              </div>
              <p class="text-xs text-ink-gray-5">
                {{
                  __(
                    "Counts from the next slot. Calls already handed out stay on their list."
                  )
                }}
              </p>
            </form>
          </div>
        </template>
      </div>
    </div>
  </div>
  <MemberLeadsDialog
    v-if="current"
    v-model:open="showLeads"
    :department="current"
    :member="leadsOf"
    :start-on-pool="leadsOnPool"
    :start-product="leadsProduct"
    @changed="plans.reload()"
  />
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  Checkbox,
  createResource,
  ErrorMessage,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideClock from "~icons/lucide/clock";
import LucideCloudOff from "~icons/lucide/cloud-off";
import LucideLock from "~icons/lucide/lock";
import LucidePhoneOff from "~icons/lucide/phone-off";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUsers from "~icons/lucide/users";
import MemberLeadsDialog from "./MemberLeadsDialog.vue";
import {
  autoAssignText,
  byIndustry,
  industryReady,
  leadsReady,
  poolStuck,
  type CallPlans,
  type PlanDepartment,
  type PlanMember,
} from "./callPlans";

// the ERP site refuses more
const MAX_CALLS = 500;

const route = useRoute();
const router = useRouter();
const peopleHeading = useId();
const planHeading = useId();

const plans = createResource<CallPlans>({
  url: "helpdesk.api.call_batches.get_call_plans",
  auto: true,
});

// a refusal (not a manager or head) is no failure to retry
const isRefusal = computed(
  () => plans.error?.exc_type === "LeadsForbiddenError"
);

// the department is in the URL, so a link or a reload opens the same one
const current = computed<PlanDepartment | undefined>(() => {
  const departments = plans.data?.departments ?? [];
  return (
    departments.find((d) => d.department === route.query.department) ??
    departments[0]
  );
});

const stuck = computed(() => (current.value ? poolStuck(current.value) : null));

const departmentOptions = computed(() =>
  (plans.data?.departments ?? []).map((d) => ({
    label: d.department,
    value: d.department,
  }))
);

function pickDepartment(name: string) {
  router.replace({ query: { ...route.query, department: name } });
}

// ---------- who is picked ----------

const picked = ref<string[]>([]);
watch(
  () => current.value?.department,
  () => {
    picked.value = [];
    fillForm();
  }
);

const isPicked = (user: string) => picked.value.includes(user);
const allPicked = computed(
  () =>
    !!current.value?.members.length &&
    picked.value.length === current.value.members.length
);

function toggle(user: string, on: boolean) {
  picked.value = on
    ? [...new Set([...picked.value, user])]
    : picked.value.filter((u) => u !== user);
}

function pickAll(on: boolean) {
  picked.value = on ? current.value?.members.map((m) => m.user) ?? [] : [];
}

const pickedMembers = computed(() =>
  (current.value?.members ?? []).filter((m) => isPicked(m.user))
);
const pickedWithPlan = computed(() =>
  pickedMembers.value.filter((m) => m.has_plan)
);
const pickedLabel = computed(() =>
  pickedMembers.value.length === 1
    ? pickedMembers.value[0].full_name
    : __("{0} people", String(pickedMembers.value.length))
);

// ---------- the plan ----------

const form = reactive<{
  product: string;
  industry: string;
  sizes: Record<string, number>;
}>({
  product: "",
  industry: "",
  sizes: {},
});
// a department without products plans and gives leads by industry (callPlans.byIndustry)
const industryMode = computed(() => byIndustry(current.value));
/** The product, or in industry mode the industry, the plan calls for ("" for any). */
const chosen = computed(() =>
  industryMode.value ? form.industry : form.product
);
const anyLabel = computed(() =>
  industryMode.value ? __("Any industry") : __("Any product")
);
function planChoice(member: PlanMember) {
  return (industryMode.value ? member.industry : member.product) || "";
}
const formError = ref("");

/** One person picked: their plan to edit. Otherwise the department's slot sizes, or what
 * the first picked person has, so a team is planned in one go. */
function fillForm(from?: PlanMember) {
  const department = current.value;
  if (!department) return;
  form.product = department.campaign_product || from?.product || "";
  form.industry = from?.industry || "";
  form.sizes = Object.fromEntries(
    department.slots.map((slot) => [
      slot.label,
      from?.sizes[slot.label] ?? slot.size,
    ])
  );
  formError.value = "";
}

watch(
  () => pickedMembers.value[0]?.user,
  () => {
    if (pickedMembers.value.length === 1) fillForm(pickedMembers.value[0]);
    else if (!pickedMembers.value.length) fillForm();
  }
);
watch(
  current,
  (department) => department && !Object.keys(form.sizes).length && fillForm(),
  {
    immediate: true,
  }
);

/** "PhoebiX · 120 unassigned": how many leads of each product wait to be handed out. */
const productOptions = computed(() => {
  const department = current.value;
  const label = (name: string, product: string | null) =>
    department
      ? __(
          "{0} · {1} unassigned",
          name,
          String(leadsReady(department, product))
        )
      : name;
  return [
    { label: label(__("Any product"), null), value: "" },
    ...(department?.products ?? []).map((p) => ({
      label: label(p.product_name, p.product_name),
      value: p.product_name,
    })),
  ];
});

const perPerson = computed(() =>
  Object.values(form.sizes).reduce(
    (sum, calls) => sum + (Number(calls) || 0),
    0
  )
);
const ready = computed(() => {
  if (!current.value) return 0;
  return industryMode.value
    ? industryReady(current.value, form.industry || null)
    : leadsReady(current.value, form.product || null);
});
/** "Hospitality · 120 unassigned", for a department planned by industry. */
const industryOptions = computed(() => {
  const department = current.value;
  if (!department) return [];
  const label = (name: string, industry: string | null) =>
    __(
      "{0} · {1} unassigned",
      name,
      String(industryReady(department, industry))
    );
  return [
    { label: label(__("Any industry"), null), value: "" },
    ...(department.industries ?? []).map((name) => ({
      label: label(name, name),
      value: name,
    })),
  ];
});
const short = computed(
  () => perPerson.value * picked.value.length > ready.value
);

function cleanSizes(): Record<string, number> | null {
  const sizes: Record<string, number> = {};
  for (const [label, value] of Object.entries(form.sizes)) {
    const calls = Number(value);
    if (!Number.isInteger(calls) || calls < 0 || calls > MAX_CALLS) {
      formError.value = __(
        "{0}: give a whole number from 0 to {1}.",
        label,
        String(MAX_CALLS)
      );
      return null;
    }
    sizes[label] = calls;
  }
  return sizes;
}

// ---------- saving ----------

const clearing = ref(false);
const save = createResource({
  url: "helpdesk.api.call_batches.save_call_plan",
  onSuccess(department: PlanDepartment) {
    if (plans.data) {
      plans.data.departments = plans.data.departments.map((d) =>
        d.department === department.department ? department : d
      );
    }
    toast.success(
      clearing.value
        ? __("Back to the department's sizes for {0}", pickedLabel.value)
        : __("Leads assigned to {0}", pickedLabel.value)
    );
    picked.value = [];
  },
  onError(error: unknown) {
    formError.value = errorText(error, __("Couldn't save. Try again."));
  },
});

function assign() {
  formError.value = "";
  if (!current.value || !picked.value.length) return;
  const sizes = cleanSizes();
  if (!sizes) return;
  clearing.value = false;
  save.submit({
    department: current.value.department,
    users: picked.value,
    product: industryMode.value ? null : form.product || null,
    ...(industryMode.value ? { industry: form.industry || null } : {}),
    sizes,
  });
}

function clearPlans() {
  formError.value = "";
  if (!current.value) return;
  clearing.value = true;
  save.submit({
    department: current.value.department,
    users: pickedWithPlan.value.map((m) => m.user),
    clear: 1,
  });
}

// ---------- a person's leads, or the unassigned ones ----------

const showLeads = ref(false);
const leadsOf = ref<PlanMember | null>(null);
const leadsOnPool = ref(false);
const leadsProduct = ref("");
function openLeads(member: PlanMember | null) {
  leadsOf.value = member;
  leadsOnPool.value = false;
  leadsProduct.value = "";
  showLeads.value = true;
}

/** The chosen product's unassigned leads, ready to give to the one person picked. */
function openPool() {
  leadsOf.value =
    pickedMembers.value.length === 1 ? pickedMembers.value[0] : null;
  leadsOnPool.value = true;
  leadsProduct.value = chosen.value;
  showLeads.value = true;
}

// ---------- give unassigned leads now ----------

// the ERP site refuses more in one call
const MAX_GIVE = 500;
const giveCount = ref<number | string>(25);
const giving = ref(false);

/** The next N unassigned leads of the chosen product to each person picked, one call each. */
async function giveNow() {
  const count = Number(giveCount.value);
  if (!Number.isInteger(count) || count < 1 || count > MAX_GIVE) {
    formError.value = __(
      "Give a whole number from 1 to {0}.",
      String(MAX_GIVE)
    );
    return;
  }
  formError.value = "";
  giving.value = true;
  let given = 0;
  try {
    for (const member of pickedMembers.value) {
      const result = await call("helpdesk.api.call_batches.assign_leads", {
        department: current.value?.department,
        user: member.user,
        count,
        ...(industryMode.value
          ? { industry: form.industry || null }
          : { product: form.product || null }),
      });
      given += Number(result?.assigned) || 0;
    }
    toast.success(
      given
        ? __("{0} leads given to {1}.", String(given), pickedLabel.value)
        : __("No unassigned leads were left to give.")
    );
  } catch (error) {
    formError.value = errorText(
      error,
      __("Couldn't give the leads. Try again.")
    );
  } finally {
    giving.value = false;
    plans.reload();
  }
}

/** "PhoebiX · 50 + 50", the plan on one line for a phone. */
function planLine(member: PlanMember) {
  const sizes = (current.value?.slots ?? [])
    .map((slot) => member.sizes[slot.label] ?? slot.size)
    .join(" + ");
  return `${planChoice(member) || anyLabel.value} · ${sizes}`;
}
</script>
