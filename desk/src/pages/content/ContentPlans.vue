<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="flex min-w-0 flex-col gap-1">
          <div
            class="flex min-w-0 items-center gap-1.5 text-lg font-bold md:text-[28px] md:leading-[1.2] md:tracking-[-0.02em]"
          >
            <router-link
              :to="{ name: 'ContentCalendar' }"
              class="truncate rounded text-ink-gray-6 hover:text-ink-gray-9"
              >{{ __("Content Calendar") }}</router-link
            >
            <LucideChevronRight
              class="size-5 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
            <h1 class="truncate text-ink-gray-9">{{ __("Monthly plans") }}</h1>
          </div>
          <p class="hidden text-[14px] text-ink-gray-6 md:block">
            {{
              __(
                "What goes out each month for every client, and the dates worth posting for."
              )
            }}
          </p>
        </div>
      </template>
      <template #right-header>
        <Button
          v-if="tab === 'plans' && plans.data?.can_edit"
          variant="solid"
          size="md"
          :label="__('New plan')"
          @click="editPlan(null)"
        >
          <template #prefix
            ><LucidePlus class="size-[18px]" aria-hidden="true"
          /></template>
        </Button>
        <Button
          v-if="tab === 'occasions' && occasions.data?.can_edit"
          variant="solid"
          size="md"
          :label="__('Add occasion')"
          @click="editOccasion(null)"
        >
          <template #prefix
            ><LucidePlus class="size-[18px]" aria-hidden="true"
          /></template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="relative min-h-0 flex-1 overflow-y-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <div class="max-w-full self-start overflow-x-auto">
          <ViewTabs
            v-model="tab"
            :aria-label="__('Monthly plans')"
            :options="
              TABS.map((t) => ({
                label: t.label,
                value: t.key,
                icon: t.icon,
              }))
            "
          />
        </div>

        <!-- customer plans -->
        <template v-if="tab === 'plans'">
          <p class="text-[13px] text-ink-gray-6">
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
            class="rounded-xl bg-danger-soft px-4 py-3.5 text-[13px] text-danger"
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
              class="h-36 animate-pulse rounded-xl bg-surface-gray-3"
            />
          </div>

          <div
            v-else-if="!planList.length"
            class="flex flex-col items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-14 text-center"
          >
            <LucideCalendarSync
              class="size-6 text-ink-gray-5"
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
              size="md"
              :label="__('New plan')"
              @click="editPlan(null)"
            />
          </div>

          <article
            v-for="plan in planList"
            :key="plan.name"
            class="flex flex-col gap-4 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
            :aria-labelledby="`plan-${plan.name}`"
          >
            <header class="flex flex-wrap items-start gap-2">
              <div class="min-w-0 flex-1">
                <h2
                  :id="`plan-${plan.name}`"
                  class="truncate text-base font-semibold text-ink-gray-9"
                >
                  {{ plan.customer }}
                </h2>
                <p class="mt-0.5 text-[12px] text-ink-gray-6">
                  {{ __(plan.posting_days) }} ·
                  {{ timeLabel(plan.publish_time) }}
                  <template v-if="plan.include_occasions">
                    · {{ occasionLabel(plan) }}</template
                  >
                </p>
              </div>
              <span
                class="inline-flex h-[26px] items-center gap-1.5 rounded-full px-2.5 text-xs font-semibold"
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
                class="inline-flex h-[26px] items-center gap-1 rounded-full bg-surface-gray-2 px-2.5 text-xs font-medium text-ink-gray-7"
              >
                <span class="font-mono tabular-nums">{{
                  item.posts_per_month
                }}</span>
                × {{ item.channel }} {{ item.format }}
              </span>
              <span
                class="inline-flex h-[26px] items-center px-1 text-xs text-ink-gray-6"
              >
                {{ __("{0} a month", String(plan.posts_per_month)) }}
              </span>
            </div>

            <dl class="flex flex-wrap gap-x-6 gap-y-2 text-[12px]">
              <div
                v-for="role in TEAM_ROLES"
                :key="role.field"
                class="flex items-center gap-2"
              >
                <dt class="text-ink-gray-6">{{ __(role.label) }}</dt>
                <dd
                  class="flex items-center gap-1.5"
                  :class="
                    plan.team[role.field]
                      ? 'font-medium text-ink-gray-8'
                      : 'text-ink-gray-5'
                  "
                >
                  <PersonAvatar
                    v-if="plan.team[role.field]"
                    :name="plan.team[role.field]"
                    size="xs"
                  />
                  {{ plan.team[role.field] || __("Not set") }}
                </dd>
              </div>
            </dl>

            <footer
              v-if="plans.data?.can_edit"
              class="-mx-5 -mb-5 flex flex-wrap items-center justify-end gap-2 border-t border-outline-gray-2 px-5 py-3.5"
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
            <span class="text-lg font-semibold tabular-nums text-ink-gray-9">{{
              year
            }}</span>
            <Button
              variant="ghost"
              :aria-label="__('Next year')"
              @click="year++"
            >
              <LucideChevronRight class="size-4" aria-hidden="true" />
            </Button>
            <p class="flex-1 text-[13px] text-ink-gray-6">
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
            class="rounded-xl bg-danger-soft px-4 py-3.5 text-[13px] text-danger"
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
              class="h-14 animate-pulse rounded-xl bg-surface-gray-3"
            />
          </div>

          <p
            v-else-if="!byMonth.length"
            class="rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-14 text-center text-p-sm text-ink-gray-6"
          >
            {{ __("No occasions in {0}.", String(year)) }}
          </p>

          <section
            v-for="month in byMonth"
            :key="month.key"
            class="flex flex-col gap-2"
            :aria-label="month.label"
          >
            <h2
              class="px-1 text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6"
            >
              {{ month.label }}
            </h2>
            <ul
              class="divide-y divide-outline-gray-1 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            >
              <li v-for="o in month.items" :key="`${o.name}-${o.date}`">
                <button
                  type="button"
                  class="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none disabled:cursor-default"
                  :disabled="!occasions.data?.can_edit"
                  @click="editOccasion(o)"
                >
                  <span
                    class="w-14 shrink-0 font-mono text-xs tabular-nums text-ink-gray-6"
                    >{{ dayjs(o.date).format("D MMM") }}</span
                  >
                  <span class="min-w-0 flex-1">
                    <span
                      class="block truncate text-[13px] font-medium text-ink-gray-9"
                      >{{ o.occasion_name }}</span
                    >
                    <span
                      v-if="o.idea"
                      class="block truncate text-[12px] text-ink-gray-6"
                      >{{ o.idea }}</span
                    >
                  </span>
                  <LucideRepeat
                    v-if="o.repeats_yearly"
                    class="size-3.5 shrink-0 text-ink-gray-6"
                    :aria-label="__('Every year')"
                  />
                  <span
                    class="inline-flex h-[26px] shrink-0 items-center rounded-full bg-surface-gray-2 px-2.5 text-xs font-medium text-ink-gray-7"
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
import PersonAvatar from "@/components/PersonAvatar.vue";
import ViewTabs from "@/components/ViewTabs.vue";
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
import { computed, markRaw, ref, watch, type Component } from "vue";
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
const TABS: { key: Tab; label: string; icon: Component }[] = [
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
