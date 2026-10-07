<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="flex items-center gap-1.5 text-lg-medium">
          <router-link
            :to="{ name: 'ContentCalendar' }"
            class="text-ink-gray-5 hover:text-ink-gray-8"
            >{{ __("Content Calendar") }}</router-link
          >
          <LucideChevronRight
            class="size-4 text-ink-gray-4"
            aria-hidden="true"
          />
          <span class="text-ink-gray-9">{{ __("Monthly plans") }}</span>
        </div>
      </template>
      <template #right-header>
        <Button
          v-if="tab === 'plans' && plans.data?.can_edit"
          variant="solid"
          :label="__('New plan')"
          @click="editPlan(null)"
        >
          <template #prefix
            ><LucidePlus class="size-4" aria-hidden="true"
          /></template>
        </Button>
        <Button
          v-if="tab === 'occasions' && occasions.data?.can_edit"
          variant="solid"
          :label="__('Add occasion')"
          @click="editOccasion(null)"
        >
          <template #prefix
            ><LucidePlus class="size-4" aria-hidden="true"
          /></template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <div class="mx-auto flex max-w-4xl flex-col gap-4 px-4 py-5 md:px-6">
        <div
          class="inline-flex self-start rounded-lg bg-surface-gray-2 p-0.5"
          role="tablist"
          :aria-label="__('Monthly plans')"
        >
          <button
            v-for="t in TABS"
            :key="t.key"
            type="button"
            role="tab"
            :aria-selected="tab === t.key"
            class="inline-flex h-7 items-center gap-1.5 rounded-md px-3 text-sm"
            :class="
              tab === t.key
                ? 'bg-surface-base text-ink-gray-9 shadow-sm'
                : 'text-ink-gray-6 hover:text-ink-gray-8'
            "
            @click="tab = t.key"
          >
            <component :is="t.icon" class="size-4" aria-hidden="true" />
            {{ t.label }}
          </button>
        </div>

        <!-- customer plans -->
        <template v-if="tab === 'plans'">
          <p class="text-p-sm text-ink-gray-6">
            {{
              __(
                "On day {0} of each month, next month's posts are created as ideas for every plan that plans automatically. Change the day in Settings → Content.",
                String(plans.data?.plan_day ?? 20)
              )
            }}
          </p>

          <div
            v-if="plans.error"
            role="alert"
            class="rounded-lg bg-danger-soft px-4 py-2.5 text-sm text-danger"
          >
            {{ errorText(plans.error, __("Couldn't load the plans.")) }}
          </div>

          <div
            v-else-if="plans.loading && !plans.data"
            class="flex flex-col gap-3"
          >
            <div
              v-for="i in 3"
              :key="i"
              class="h-28 animate-pulse rounded-lg bg-surface-gray-2"
            />
          </div>

          <div
            v-else-if="!planList.length"
            class="flex flex-col items-center gap-3 rounded-lg border border-dashed border-outline-gray-3 px-4 py-12 text-center"
          >
            <LucideCalendarSync
              class="size-6 text-ink-gray-4"
              aria-hidden="true"
            />
            <p class="max-w-md text-p-sm text-ink-gray-6">
              {{
                __(
                  "No monthly plans yet. Add one per customer: what goes out each month and who does it."
                )
              }}
            </p>
            <Button
              v-if="plans.data?.can_edit"
              variant="solid"
              :label="__('New plan')"
              @click="editPlan(null)"
            />
          </div>

          <article
            v-for="plan in planList"
            :key="plan.name"
            class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-base px-4 py-3"
            :aria-labelledby="`plan-${plan.name}`"
          >
            <header class="flex flex-wrap items-start gap-2">
              <div class="min-w-0 flex-1">
                <h2
                  :id="`plan-${plan.name}`"
                  class="truncate text-base font-medium text-ink-gray-9"
                >
                  {{ plan.customer }}
                </h2>
                <p class="text-xs text-ink-gray-5">
                  {{ __(plan.posting_days) }} ·
                  {{ timeLabel(plan.publish_time) }}
                  <template v-if="plan.include_occasions">
                    · {{ occasionLabel(plan) }}</template
                  >
                </p>
              </div>
              <span
                class="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs"
                :class="
                  plan.next_month_planned
                    ? 'bg-success-soft text-success'
                    : plan.enabled
                    ? 'bg-info-soft text-info'
                    : 'bg-surface-gray-2 text-ink-gray-6'
                "
              >
                <component
                  :is="
                    plan.next_month_planned
                      ? LucideCircleCheck
                      : plan.enabled
                      ? LucideClock
                      : LucidePause
                  "
                  class="size-3.5"
                  aria-hidden="true"
                />
                {{ planState(plan) }}
              </span>
            </header>

            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="(item, i) in plan.items"
                :key="i"
                class="rounded bg-surface-gray-2 px-2 py-0.5 text-xs text-ink-gray-7"
              >
                <span class="font-mono tabular-nums">{{
                  item.posts_per_month
                }}</span>
                × {{ item.channel }} {{ item.format }}
              </span>
              <span class="px-1 py-0.5 text-xs text-ink-gray-5">
                {{ __("{0} a month", String(plan.posts_per_month)) }}
              </span>
            </div>

            <dl class="flex flex-wrap gap-x-6 gap-y-1 text-xs">
              <div
                v-for="role in TEAM_ROLES"
                :key="role.field"
                class="flex gap-1.5"
              >
                <dt class="text-ink-gray-5">{{ __(role.label) }}</dt>
                <dd
                  :class="
                    plan.team[role.field]
                      ? 'text-ink-gray-8'
                      : 'text-ink-gray-4'
                  "
                >
                  {{ plan.team[role.field] || __("Not set") }}
                </dd>
              </div>
            </dl>

            <footer
              v-if="plans.data?.can_edit"
              class="flex flex-wrap items-center justify-end gap-2 border-t border-outline-gray-1 pt-3"
            >
              <Button
                size="sm"
                variant="ghost"
                :label="__('Edit')"
                @click="editPlan(plan)"
              >
                <template #prefix
                  ><LucidePencil class="size-3.5" aria-hidden="true"
                /></template>
              </Button>
              <Dropdown :options="moreActions(plan)" align="end">
                <Button
                  size="sm"
                  variant="ghost"
                  :aria-label="__('More actions for {0}', plan.customer)"
                >
                  <LucideEllipsis class="size-4" aria-hidden="true" />
                </Button>
              </Dropdown>
              <Button
                size="sm"
                variant="subtle"
                :label="
                  __(
                    'Plan {0} now',
                    dayjs(plans.data.next_month).format('MMMM')
                  )
                "
                :disabled="plan.next_month_planned"
                :loading="planning === `${plan.name}:next`"
                @click="planNow(plan, 'next')"
              />
            </footer>
          </article>
        </template>

        <!-- occasions -->
        <template v-else>
          <div class="flex flex-wrap items-center gap-2">
            <Button
              variant="ghost"
              :aria-label="__('Previous year')"
              @click="year--"
            >
              <LucideChevronLeft class="size-4" aria-hidden="true" />
            </Button>
            <span class="text-base font-medium tabular-nums text-ink-gray-9">{{
              year
            }}</span>
            <Button
              variant="ghost"
              :aria-label="__('Next year')"
              @click="year++"
            >
              <LucideChevronRight class="size-4" aria-hidden="true" />
            </Button>
            <p class="flex-1 text-p-sm text-ink-gray-6">
              {{
                __(
                  "Festivals that move each year (Diwali, Onam, Vishu, Eid, Ramadan, Holi) need that year's date."
                )
              }}
            </p>
          </div>

          <div
            v-if="occasions.error"
            role="alert"
            class="rounded-lg bg-danger-soft px-4 py-2.5 text-sm text-danger"
          >
            {{
              occasions.error?.messages?.[0] ||
              __("Couldn't load the occasions.")
            }}
          </div>

          <div
            v-else-if="occasions.loading && !occasions.data"
            class="flex flex-col gap-2"
          >
            <div
              v-for="i in 5"
              :key="i"
              class="h-10 animate-pulse rounded bg-surface-gray-2"
            />
          </div>

          <p
            v-else-if="!byMonth.length"
            class="rounded-lg border border-dashed border-outline-gray-3 px-4 py-10 text-center text-p-sm text-ink-gray-6"
          >
            {{ __("No occasions in {0}.", String(year)) }}
          </p>

          <section
            v-for="month in byMonth"
            :key="month.key"
            class="flex flex-col gap-1"
            :aria-label="month.label"
          >
            <h2
              class="text-2xs font-semibold uppercase tracking-[0.06em] text-ink-gray-5"
            >
              {{ month.label }}
            </h2>
            <ul
              class="divide-y divide-outline-gray-1 overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-base"
            >
              <li v-for="o in month.items" :key="`${o.name}-${o.date}`">
                <button
                  type="button"
                  class="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none disabled:cursor-default"
                  :disabled="!occasions.data?.can_edit"
                  @click="editOccasion(o)"
                >
                  <span
                    class="w-14 shrink-0 font-mono text-xs tabular-nums text-ink-gray-6"
                    >{{ dayjs(o.date).format("D MMM") }}</span
                  >
                  <span class="min-w-0 flex-1">
                    <span class="block truncate text-sm text-ink-gray-9">{{
                      o.occasion_name
                    }}</span>
                    <span
                      v-if="o.idea"
                      class="block truncate text-xs text-ink-gray-5"
                      >{{ o.idea }}</span
                    >
                  </span>
                  <LucideRepeat
                    v-if="o.repeats_yearly"
                    class="size-3.5 shrink-0 text-ink-gray-4"
                    :aria-label="__('Every year')"
                  />
                  <span
                    class="shrink-0 rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-6"
                    >{{ __(o.region) }}</span
                  >
                </button>
              </li>
            </ul>
          </section>
        </template>
      </div>
    </div>

    <PlanDialog
      v-model:open="planOpen"
      :plan="selectedPlan"
      @saved="plans.reload()"
    />
    <OccasionDialog
      v-model:open="occasionOpen"
      :occasion="selectedOccasion"
      @saved="occasions.reload()"
    />
    <Dialog
      v-model:open="deleteOpen"
      :options="{
        title: __('Delete this plan?'),
        message: __(
          'Posts already planned stay on the calendar. Nothing new is planned for {0}.',
          deletingPlan?.customer || ''
        ),
        actions: [
          {
            label: __('Delete plan'),
            variant: 'solid',
            theme: 'red',
            onClick: confirmDelete,
          },
        ],
      }"
    />
  </div>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { __ } from "@/translation";
import {
  Button,
  call,
  createResource,
  dayjs,
  Dialog,
  Dropdown,
  toast,
} from "frappe-ui";
import { useStorage } from "@vueuse/core";
import { computed, markRaw, ref, watch } from "vue";
import LucideCalendarDays from "~icons/lucide/calendar-days";
import LucideCalendarSync from "~icons/lucide/calendar-sync";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucidePause from "~icons/lucide/pause";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlus from "~icons/lucide/plus";
import LucideRepeat from "~icons/lucide/repeat";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideTrash2 from "~icons/lucide/trash-2";
import { TEAM_ROLES } from "./constants";
import OccasionDialog, { type Occasion } from "./components/OccasionDialog.vue";
import PlanDialog, { type ContentPlan } from "./components/PlanDialog.vue";

type Tab = "plans" | "occasions";
const TABS: { key: Tab; label: string; icon: unknown }[] = [
  {
    key: "plans",
    label: __("Customer plans"),
    icon: markRaw(LucideCalendarDays),
  },
  { key: "occasions", label: __("Occasions"), icon: markRaw(LucideSparkles) },
];
const tab = useStorage<Tab>("helpdesk-content-plans-tab", "plans");

const plans = createResource({
  url: "helpdesk.api.content_plans.get_plans",
  auto: true,
});
const planList = computed<ContentPlan[]>(() => plans.data?.plans ?? []);

const year = ref(dayjs().year());
const occasions = createResource({
  url: "helpdesk.api.content_plans.get_occasions_for_year",
  makeParams: () => ({ year: year.value }),
  auto: true,
});
watch(year, () => occasions.reload());

const byMonth = computed(() => {
  const groups = new Map<
    string,
    { key: string; label: string; items: Occasion[] }
  >();
  for (const o of (occasions.data?.occasions ?? []) as Occasion[]) {
    const key = o.date.slice(0, 7);
    if (!groups.has(key))
      groups.set(key, { key, label: dayjs(o.date).format("MMMM"), items: [] });
    groups.get(key)!.items.push(o);
  }
  return [...groups.values()];
});

function timeLabel(value?: string) {
  return value ? dayjs(`2000-01-01 ${value}`).format("h:mm A") : "";
}

function occasionLabel(plan: ContentPlan) {
  const regions = [
    plan.occasions_india && __("India"),
    plan.occasions_kerala && __("Kerala"),
    plan.occasions_uae && __("UAE"),
  ].filter(Boolean);
  return regions.length
    ? __("Occasions: {0}", regions.join(", "))
    : __("Occasions: everywhere only");
}

function planState(plan: ContentPlan) {
  const next = dayjs(plans.data?.next_month).format("MMMM");
  if (plan.next_month_planned) return __("{0} planned", next);
  if (!plan.enabled) return __("Paused");
  return __("Plans {0} on day {1}", next, String(plans.data?.plan_day ?? 20));
}

// --- dialogs and actions ---

const planOpen = ref(false);
const selectedPlan = ref<ContentPlan | null>(null);
function editPlan(plan: ContentPlan | null) {
  selectedPlan.value = plan;
  planOpen.value = true;
}

const occasionOpen = ref(false);
const selectedOccasion = ref<Occasion | null>(null);
function editOccasion(o: Occasion | null) {
  selectedOccasion.value = o;
  occasionOpen.value = true;
}

const planning = ref("");
async function planNow(plan: ContentPlan, which: "this" | "next") {
  planning.value = `${plan.name}:${which}`;
  try {
    const count = await call("helpdesk.api.content_plans.plan_now", {
      name: plan.name,
      which,
    });
    toast.success(__("{0} posts added to the Content Calendar", String(count)));
    plans.reload();
  } catch (e: any) {
    toast.error(e?.messages?.[0] || __("Couldn't plan this month."));
  } finally {
    planning.value = "";
  }
}

const deleteOpen = ref(false);
const deletingPlan = ref<ContentPlan | null>(null);
async function confirmDelete({ close }: { close: () => void }) {
  if (!deletingPlan.value) return;
  try {
    await call("helpdesk.api.content_plans.delete_plan", {
      name: deletingPlan.value.name,
    });
    toast.success(__("Plan deleted"));
    plans.reload();
    close();
  } catch (e: any) {
    toast.error(e?.messages?.[0] || __("Couldn't delete the plan."));
  }
}

function moreActions(plan: ContentPlan) {
  return [
    {
      label: __("Plan the rest of this month"),
      icon: LucideCalendarSync,
      onClick: () => planNow(plan, "this"),
    },
    {
      label: __("Delete plan"),
      icon: LucideTrash2,
      onClick: () => {
        deletingPlan.value = plan;
        deleteOpen.value = true;
      },
    },
  ];
}
</script>
