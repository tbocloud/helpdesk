<template>
  <Dialog
    :open="open"
    size="3xl"
    :title="title"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <div class="flex flex-col gap-3">
      <TabButtons
        v-if="member"
        :model-value="view"
        class="self-start"
        :aria-label="__('Leads to show')"
        :options="[
          { label: __('Their leads'), value: 'theirs' },
          { label: __('Unassigned'), value: 'pool' },
        ]"
        @update:model-value="setView(String($event) as View)"
      />

      <div class="flex flex-wrap items-end gap-3">
        <FormControl
          v-model="filters.product"
          type="select"
          class="w-full sm:w-56"
          :label="__('Product')"
          :options="productFilter"
        />
        <FormControl
          v-model="filters.search"
          type="search"
          class="min-w-0 flex-1"
          :label="__('Search')"
          :placeholder="__('Name, company or phone')"
        />
      </div>

      <!-- give the next N leads of the pool without picking them one by one -->
      <form
        v-if="member && view === 'pool'"
        class="flex flex-wrap items-end gap-3 rounded-lg bg-surface-gray-1 p-3"
        novalidate
        @submit.prevent="giveByNumber"
      >
        <FormControl
          v-model="give.count"
          type="number"
          min="1"
          :max="MAX_LEADS"
          inputmode="numeric"
          class="w-28"
          :label="__('Give the next')"
        />
        <FormControl
          v-model="give.product"
          type="select"
          class="w-full sm:w-48"
          :label="__('Of product')"
          :options="productChoices(__('Any product'))"
        />
        <Button
          type="submit"
          :label="__('Give to {0}', firstName)"
          :loading="busy === 'give'"
          :disabled="!!busy"
        />
      </form>

      <section
        class="min-w-0 rounded-lg border border-outline-gray-2"
        :aria-label="title"
        :aria-busy="leads.loading"
      >
        <div
          class="flex items-center gap-3 border-b border-outline-gray-1 px-3 py-2"
        >
          <Checkbox
            v-if="rows.length"
            :model-value="allPicked"
            :aria-label="__('Pick all shown')"
            @update:model-value="pickAll(!!$event)"
          />
          <span class="flex-1 text-sm text-ink-gray-6 tabular-nums">
            {{
              picked.length
                ? __("{0} picked", String(picked.length))
                : __("{0} leads", String(leads.data?.total ?? 0))
            }}
            <template v-if="!picked.length">
              &middot;
              {{
                view === "theirs" && member
                  ? __("owned by {0}", member.full_name)
                  : __("no owner yet")
              }}
            </template>
          </span>
        </div>

        <div
          v-if="leads.error && !rows.length"
          class="flex flex-col items-center gap-2 px-4 py-10 text-center"
          role="alert"
        >
          <p class="text-p-sm text-ink-gray-7">
            {{ errorText(leads.error, __("Couldn't load the leads.")) }}
          </p>
          <Button :label="__('Try again')" @click="load(0, true)" />
        </div>
        <div
          v-else-if="leads.loading && !rows.length"
          class="flex flex-col gap-2 p-3"
          :aria-label="__('Loading')"
        >
          <div
            v-for="i in 5"
            :key="i"
            class="h-10 animate-pulse rounded bg-surface-gray-2"
          />
        </div>
        <p
          v-else-if="!rows.length"
          class="px-4 py-10 text-center text-p-sm text-ink-gray-6"
        >
          {{ emptyText }}
        </p>

        <ul
          v-else
          class="max-h-[50vh] divide-y divide-outline-gray-1 overflow-y-auto"
        >
          <li v-for="lead in rows" :key="lead.name">
            <label
              class="grid cursor-pointer grid-cols-[2rem_minmax(0,1fr)] items-center gap-x-2 gap-y-0.5 px-3 py-2.5 hover:bg-surface-gray-1 sm:grid-cols-[2rem_minmax(0,1fr)_8rem_8rem]"
            >
              <Checkbox
                :model-value="picked.includes(lead.name)"
                :aria-label="lead.company_name || lead.lead_name || lead.name"
                @update:model-value="toggle(lead.name, !!$event)"
              />
              <span class="min-w-0">
                <span class="block truncate text-base text-ink-gray-9">
                  {{ lead.company_name || lead.lead_name || lead.name }}
                </span>
                <span class="block truncate text-sm text-ink-gray-6">
                  {{ [lead.stage, lead.phone].filter(Boolean).join(" · ") }}
                </span>
              </span>
              <span
                class="col-start-2 truncate text-sm sm:col-start-auto"
                :class="lead.product ? 'text-ink-gray-8' : 'text-ink-gray-5'"
              >
                {{ lead.product || __("No product") }}
              </span>
              <span
                class="col-start-2 hidden truncate font-mono text-xs text-ink-gray-5 sm:col-start-auto sm:block sm:text-right"
              >
                {{ lead.name }}
              </span>
            </label>
          </li>
        </ul>
        <div
          v-if="rows.length < (leads.data?.total ?? 0)"
          class="border-t border-outline-gray-1 p-2 text-center"
        >
          <Button
            variant="ghost"
            :label="__('Show more')"
            :loading="leads.loading"
            @click="load(rows.length)"
          />
        </div>
      </section>

      <!-- what to do with the picked leads -->
      <div
        v-if="picked.length"
        class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 p-3"
      >
        <div class="flex flex-wrap items-end gap-3">
          <FormControl
            v-model="act.product"
            type="select"
            class="w-full sm:w-48"
            :label="__('Set product')"
            :options="productChoices(__('No product'))"
          />
          <Button
            :label="__('Set product')"
            :loading="busy === 'product'"
            :disabled="!!busy"
            @click="setProduct"
          />
        </div>
        <div v-if="view === 'theirs'" class="flex flex-wrap items-end gap-3">
          <FormControl
            v-model="act.to"
            type="select"
            class="w-full sm:w-56"
            :label="__('Move to')"
            :options="moveChoices"
          />
          <Button
            :label="__('Move')"
            :loading="busy === 'move'"
            :disabled="!!busy || !act.to"
            @click="move"
          />
          <Button
            class="sm:ml-auto"
            variant="ghost"
            :label="__('Send {0} back to the pool', String(picked.length))"
            :loading="busy === 'unassign'"
            :disabled="!!busy"
            @click="confirmPool = true"
          />
        </div>
        <Button
          v-else-if="member"
          variant="solid"
          :label="__('Give {0} to {1}', String(picked.length), firstName)"
          :loading="busy === 'assign'"
          :disabled="!!busy"
          @click="assignPicked"
        />
      </div>

      <ErrorMessage v-if="actionError" :message="actionError" role="alert" />
      <p
        v-else-if="resultText"
        class="rounded-lg bg-success-soft px-3 py-2 text-sm text-ink-gray-9"
        role="status"
      >
        {{ resultText }}
      </p>
    </div>
  </Dialog>

  <!-- sending leads back takes them from the person, notes included: ask first -->
  <Dialog
    v-model="confirmPool"
    :options="{ title: __('Send these leads back to the pool?') }"
  >
    <template #body-content>
      <p class="text-p-base text-ink-gray-8">
        {{
          member
            ? __(
                "{0} leads go back to the pool. {1} will no longer see them or their notes. They go to the next person's call batch.",
                String(picked.length),
                member.full_name
              )
            : __("{0} leads go back to the pool.", String(picked.length))
        }}
      </p>
    </template>
    <template #actions>
      <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button
          variant="subtle"
          theme="red"
          :label="__('Send back to the pool')"
          @click="unassign"
        />
        <Button
          variant="solid"
          :label="__('Keep them with {0}', firstName)"
          @click="confirmPool = false"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { watchDebounced } from "@vueuse/core";
import {
  Button,
  call,
  Checkbox,
  createResource,
  Dialog,
  ErrorMessage,
  FormControl,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import type {
  DepartmentLead,
  DepartmentLeads,
  PlanDepartment,
  PlanMember,
} from "./callPlans";

type View = "theirs" | "pool";

const props = defineProps<{
  open: boolean;
  department: PlanDepartment;
  /** the person whose leads open first; null: the unassigned pool */
  member: PlanMember | null;
  /** open on the unassigned leads (to give to `member`) instead of theirs */
  startOnPool?: boolean;
  /** the product the list opens on ("" or none: every product) */
  startProduct?: string;
}>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  /** leads moved: the counts on the page are out of date */
  (e: "changed"): void;
}>();

// the ERP site refuses more in one call
const MAX_LEADS = 500;
const PAGE = 50;

const view = ref<View>("theirs");
const filters = reactive({ product: "", search: "" });
const rows = ref<DepartmentLead[]>([]);
const picked = ref<string[]>([]);
const give = reactive({ count: 25, product: "" });
const act = reactive({ product: "", to: "" });
const busy = ref<"" | "give" | "assign" | "move" | "unassign" | "product">("");
const actionError = ref("");
const resultText = ref("");
const confirmPool = ref(false);

const firstName = computed(
  () => props.member?.full_name.split(" ")[0] ?? __("them")
);
const title = computed(() =>
  props.member && view.value === "theirs"
    ? __("{0}'s leads", props.member.full_name)
    : __("Unassigned leads in {0}", props.department.department)
);
const emptyText = computed(() =>
  filters.product || filters.search
    ? __("No leads match. Clear the product or the search.")
    : view.value === "theirs"
    ? __(
        "{0} has no open leads in {1}.",
        firstName.value,
        props.department.department
      )
    : __("No unassigned leads are waiting in {0}.", props.department.department)
);

const leads = createResource<DepartmentLeads>({
  url: "helpdesk.api.call_batches.get_department_leads",
});

// the list last asked for: a view change sets the product and the search, and their
// watchers must not ask again for the same list
let lastAsked = "";
function load(start = 0, again = false) {
  const params = {
    department: props.department.department,
    owner: view.value === "theirs" ? props.member?.user : "",
    product: filters.product || null,
    search: filters.search || null,
    start,
    page_length: PAGE,
  };
  const key = JSON.stringify(params);
  if (key === lastAsked && !again) return;
  lastAsked = key;
  if (!start) picked.value = [];
  // an older page or filter's answer must not land over this one
  leads.abort();
  leads.submit(params, {
    onSuccess(data: DepartmentLeads) {
      rows.value = start ? [...rows.value, ...data.rows] : data.rows;
    },
  });
}

function setView(next: View) {
  view.value = next;
  filters.product = "";
  filters.search = "";
  load();
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    view.value = props.member && !props.startOnPool ? "theirs" : "pool";
    filters.product = props.startProduct ?? "";
    filters.search = "";
    actionError.value = "";
    resultText.value = "";
    give.product = props.startProduct || props.member?.product || "";
    load(0, true);
  },
  { immediate: true }
);
watch(
  () => filters.product,
  () => props.open && load()
);
watchDebounced(
  () => filters.search,
  () => props.open && load(),
  {
    debounce: 300,
  }
);

// ---------- picking ----------

const allPicked = computed(
  () => !!rows.value.length && picked.value.length === rows.value.length
);
function toggle(name: string, on: boolean) {
  picked.value = on
    ? [...new Set([...picked.value, name])]
    : picked.value.filter((n) => n !== name);
}
function pickAll(on: boolean) {
  picked.value = on ? rows.value.map((r) => r.name) : [];
}

// ---------- choices ----------

const productNames = computed(() =>
  props.department.products.map((p) => p.product_name)
);
const productFilter = computed(() => {
  const counts = leads.data?.products ?? {};
  const label = (name: string, key: string) =>
    counts[key] === undefined ? name : `${name} (${counts[key]})`;
  return [
    { label: __("All products"), value: "" },
    ...productNames.value.map((name) => ({
      label: label(name, name),
      value: name,
    })),
    { label: label(__("No product"), ""), value: "-" },
  ];
});
function productChoices(blank: string) {
  return [
    { label: blank, value: "" },
    ...productNames.value.map((name) => ({ label: name, value: name })),
  ];
}
const moveChoices = computed(() => [
  { label: __("Choose a person"), value: "" },
  ...props.department.members
    .filter((m) => m.user !== props.member?.user)
    .map((m) => ({ label: m.full_name, value: m.user })),
]);

// ---------- acting ----------

async function run(
  kind: NonNullable<typeof busy.value>,
  method: string,
  params: Record<string, unknown>,
  done: (result: any) => string
) {
  actionError.value = "";
  resultText.value = "";
  busy.value = kind;
  try {
    const result = await call(method, params);
    resultText.value = done(result);
    toast.success(resultText.value);
    load(0, true);
    emit("changed");
  } catch (error) {
    actionError.value = errorText(error, __("Couldn't do that. Try again."));
  } finally {
    busy.value = "";
  }
}

const skippedNote = (result: { skipped?: unknown[] }) =>
  result.skipped?.length
    ? " " + __("{0} skipped.", String(result.skipped.length))
    : "";

function giveByNumber() {
  const count = Number(give.count);
  if (!Number.isInteger(count) || count < 1 || count > MAX_LEADS) {
    actionError.value = __(
      "Give a whole number from 1 to {0}.",
      String(MAX_LEADS)
    );
    return;
  }
  run(
    "give",
    "helpdesk.api.call_batches.assign_leads",
    {
      department: props.department.department,
      user: props.member?.user,
      count,
      product: give.product || null,
    },
    (r) => __("{0} leads given to {1}.", String(r.assigned), firstName.value)
  );
}

function assignPicked() {
  run(
    "assign",
    "helpdesk.api.call_batches.assign_leads",
    {
      department: props.department.department,
      user: props.member?.user,
      leads: picked.value,
    },
    (r) =>
      __("{0} leads assigned to {1}.", String(r.assigned), firstName.value) +
      skippedNote(r)
  );
}

function move() {
  const to = props.department.members.find((m) => m.user === act.to);
  run(
    "move",
    "helpdesk.api.call_batches.assign_leads",
    {
      department: props.department.department,
      user: act.to,
      leads: picked.value,
    },
    (r) =>
      __("{0} leads moved to {1}.", String(r.assigned), to?.full_name ?? "") +
      skippedNote(r)
  );
}

function unassign() {
  confirmPool.value = false;
  run(
    "unassign",
    "helpdesk.api.call_batches.unassign_leads",
    { department: props.department.department, leads: picked.value },
    (r) =>
      __("{0} leads are now in the pool.", String(r.unassigned)) +
      skippedNote(r)
  );
}

function setProduct() {
  run(
    "product",
    "helpdesk.api.leads.bulk_set_lead_category",
    { leads: picked.value, values: { product: act.product } },
    (r) => __("Product set on {0} leads.", String(r.updated)) + skippedNote(r)
  );
}
</script>
