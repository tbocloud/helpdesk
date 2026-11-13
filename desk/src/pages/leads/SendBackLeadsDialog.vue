<template>
  <Dialog
    :open="open"
    size="md"
    :title="title"
    @update:open="(value: boolean) => !value && close()"
  >
    <div class="flex flex-col gap-4">
      <p class="text-p-sm text-ink-gray-7">
        {{
          __(
            "Choose which of their open leads go back. Won and lost leads stay theirs."
          )
        }}
      </p>

      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FormControl
          v-model="scope.what"
          type="select"
          :label="industryMode ? __('Industry') : __('Product')"
          :options="whatOptions"
          :disabled="running"
        />
        <FormControl
          v-if="withDistricts"
          v-model="scope.district"
          type="select"
          :label="__('District')"
          :options="districtOptions"
          :disabled="running"
        />
      </div>

      <!-- what will happen, in numbers; while it runs, how far it got -->
      <div
        class="flex flex-col gap-1 rounded-lg bg-surface-gray-1 px-3 py-2.5 text-p-sm"
        aria-live="polite"
      >
        <template v-if="running">
          <p class="text-ink-gray-9">
            {{
              __(
                "Sending back: {0} of {1} done.",
                String(done),
                String(total ?? 0)
              )
            }}
          </p>
          <p class="text-ink-gray-6">
            {{ __("Keep this page open until it finishes.") }}
          </p>
        </template>
        <p v-else-if="total === null" class="text-ink-gray-6">
          {{ countError || __("Counting their leads…") }}
        </p>
        <p v-else-if="!total" class="text-ink-gray-7">
          {{
            __(
              "None of their open leads match. Choose another {0} or district.",
              industryMode ? __("industry") : __("product")
            )
          }}
        </p>
        <p v-else class="text-ink-gray-8">{{ summary }}</p>
      </div>

      <ErrorMessage v-if="error" :message="error" role="alert" />

      <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button
          variant="solid"
          :label="__('Keep them')"
          :disabled="running"
          @click="close"
        />
        <Button
          variant="subtle"
          theme="red"
          :label="
            total
              ? __('Send {0} back to the pool', String(total))
              : __('Send back to the pool')
          "
          :loading="running"
          :disabled="running || counting || !total"
          @click="sendBack"
        />
      </div>
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  Dialog,
  ErrorMessage,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import {
  byIndustry,
  hasDistricts,
  type DepartmentLeads,
  type PlanDepartment,
  type PlanMember,
} from "./callPlans";

/**
 * Takes the open leads of the people picked on Assign leads back to the department's
 * unassigned pool, all of them or one product's (or industry's) and district's (docs/leads.md,
 * "Assign leads"). The hub lists and takes back at most 100 at a time, so it works through
 * them in rounds, each reading what the person still has: a lead moved meanwhile is never
 * taken from its new owner.
 */
const props = defineProps<{
  open: boolean;
  department: PlanDepartment;
  /** the people picked who have open leads */
  people: PlanMember[];
}>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  /** leads went back: the counts on the page are out of date */
  (e: "changed"): void;
}>();

// the most the hub lists in one call
const CHUNK = 100;

const industryMode = computed(() => byIndustry(props.department));
const withDistricts = computed(() => hasDistricts(props.department));

// the people as they were when it opened: the page reads itself again every 15 seconds
const who = ref<PlanMember[]>([]);
const scope = reactive({ what: "", district: "" });
/** each person's open leads in the scope chosen; null while counting */
const owned = ref<Record<string, number> | null>(null);
/** their open leads per product, industry and district, whatever the scope */
const spread = ref<{
  products: Record<string, number>;
  industries: Record<string, number>;
  districts: Record<string, number>;
}>({ products: {}, industries: {}, districts: {} });
const counting = ref(false);
const countError = ref("");
const running = ref(false);
const done = ref(0);
const error = ref("");

const total = computed(() =>
  owned.value === null
    ? null
    : Object.values(owned.value).reduce((sum, n) => sum + n, 0)
);
const firstName = (member: PlanMember) => member.full_name.split(" ")[0];
const title = computed(() =>
  who.value.length === 1
    ? __("Send {0}'s leads back to the pool", who.value[0].full_name)
    : __(
        "Send the leads of {0} people back to the pool",
        String(who.value.length)
      )
);
const summary = computed(() =>
  who.value.length === 1
    ? __(
        "{0} leads go back to {1}'s unassigned pool. {2} will no longer see them or their notes, and their calls not made yet leave {2}'s list.",
        String(total.value),
        props.department.department,
        firstName(who.value[0])
      )
    : __(
        "{0} leads go back to {1}'s unassigned pool. They will no longer see them or their notes, and their calls not made yet leave their lists.",
        String(total.value),
        props.department.department
      )
);

/** A choice of `all` with every lead, then each name the people have leads of, with how many;
 * `none` ("-") for the leads without one. */
function choices(counts: Record<string, number>, all: string, none: string) {
  const sum = Object.values(counts).reduce((a, b) => a + b, 0);
  return [
    { label: `${all} (${sum})`, value: "" },
    ...Object.entries(counts)
      .filter(([name, n]) => name && n)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, n]) => ({ label: `${name} (${n})`, value: name })),
    ...(counts[""] ? [{ label: `${none} (${counts[""]})`, value: "-" }] : []),
  ];
}
const whatOptions = computed(() =>
  industryMode.value
    ? choices(spread.value.industries, __("All industries"), __("No industry"))
    : choices(spread.value.products, __("All products"), __("No product"))
);
const districtOptions = computed(() =>
  choices(spread.value.districts, __("All districts"), __("No district"))
);

function scopeParams() {
  return {
    ...(industryMode.value
      ? { industry: scope.what || null }
      : { product: scope.what || null }),
    district: scope.district || null,
  };
}

function leadsOf(member: PlanMember, pageLength: number) {
  return call("helpdesk.api.call_batches.get_department_leads", {
    department: props.department.department,
    owner: member.user,
    ...scopeParams(),
    start: 0,
    page_length: pageLength,
  }) as Promise<DepartmentLeads>;
}

// an answer for an older scope must not land over the newest one
let asked = 0;
async function count() {
  const ask = ++asked;
  counting.value = true;
  countError.value = "";
  owned.value = null;
  try {
    const answers = await Promise.all(who.value.map((m) => leadsOf(m, 1)));
    if (ask !== asked) return;
    owned.value = Object.fromEntries(
      who.value.map((m, i) => [m.user, answers[i].total])
    );
    const add = (
      key: "products" | "industries" | "districts"
    ): Record<string, number> => {
      const sums: Record<string, number> = {};
      for (const answer of answers)
        for (const [name, n] of Object.entries(answer[key] ?? {}))
          sums[name] = (sums[name] ?? 0) + n;
      return sums;
    };
    spread.value = {
      products: add("products"),
      industries: add("industries"),
      districts: add("districts"),
    };
  } catch (e) {
    if (ask === asked)
      countError.value = errorText(e, __("Couldn't count their leads."));
  } finally {
    if (ask === asked) counting.value = false;
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    who.value = [...props.people];
    scope.what = "";
    scope.district = "";
    spread.value = { products: {}, industries: {}, districts: {} };
    done.value = 0;
    error.value = "";
    count();
  },
  { immediate: true }
);
watch(
  () => [scope.what, scope.district],
  () => props.open && !running.value && count()
);

function close() {
  if (!running.value) emit("update:open", false);
}

async function sendBack() {
  const counted = owned.value;
  if (!counted || !total.value) return;
  const planned = total.value;
  running.value = true;
  done.value = 0;
  error.value = "";
  let failed = false;
  try {
    for (const member of who.value) {
      // never more than were counted: leads handed to the person meanwhile stay theirs
      let left = counted[member.user] ?? 0;
      while (left > 0) {
        const page = await leadsOf(member, Math.min(CHUNK, left));
        const names = page.rows.map((r) => r.name);
        if (!names.length) break;
        const result = await call("helpdesk.api.call_batches.unassign_leads", {
          department: props.department.department,
          leads: names,
        });
        const moved = Number(result?.unassigned) || 0;
        done.value += moved;
        left -= moved;
        if (!moved) break;
      }
    }
  } catch (e) {
    failed = true;
    error.value = __(
      "{0} of {1} went back before it stopped: {2}",
      String(done.value),
      String(planned),
      errorText(e, __("the ERP site didn't answer."))
    );
  } finally {
    running.value = false;
  }
  emit("changed");
  if (failed) {
    // count what is left, so sending again takes the rest
    count();
    return;
  }
  toast.success(__("{0} leads are now in the pool.", String(done.value)));
  close();
}
</script>
