<template>
  <SettingsLayoutBase
    :title="__('Ticket intake')"
    :description="
      __(
        'Which mail becomes a ticket, how monitoring alerts group, where triaged tickets go and how customers are recognised.'
      )
    "
    :dirty="isDirty"
    :saving="save.loading"
    :loading="!form && !settings.error"
    :error="settings.error"
    @retry="settings.reload()"
    @save="save.submit()"
  >
    <template #content>
      <div v-if="form">
        <SettingsSection
          :title="__('Mail rules')"
          :description="
            __(
              'Checked in this order on every new mail; the first match decides. Replies to a ticket are never filtered.'
            )
          "
        >
          <ol
            v-if="form.rules.length"
            class="flex flex-col divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2"
            :aria-label="__('Mail rules')"
          >
            <li
              v-for="(rule, index) in form.rules"
              :key="index"
              class="flex min-w-0 flex-col gap-3 p-3 sm:p-4"
              :class="!rule.enabled && 'bg-surface-gray-1'"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span class="font-mono text-xs tabular-nums text-ink-gray-5">
                  {{ index + 1 }}
                </span>
                <div class="flex items-center gap-1">
                  <Switch v-model="rule.enabled" size="sm" :label="__('On')" />
                  <Button
                    variant="ghost"
                    :aria-label="__('Move {0} up', rule.label || __('rule'))"
                    :disabled="index === 0"
                    @click="move(index, -1)"
                  >
                    <LucideArrowUp class="size-4" aria-hidden="true" />
                  </Button>
                  <Button
                    variant="ghost"
                    :aria-label="__('Move {0} down', rule.label || __('rule'))"
                    :disabled="index === form.rules.length - 1"
                    @click="move(index, 1)"
                  >
                    <LucideArrowDown class="size-4" aria-hidden="true" />
                  </Button>
                  <Button
                    variant="ghost"
                    :aria-label="__('Remove {0}', rule.label || __('rule'))"
                    @click="form.rules.splice(index, 1)"
                  >
                    <LucideTrash2 class="size-4" aria-hidden="true" />
                  </Button>
                </div>
              </div>
              <div
                class="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_12rem]"
              >
                <FormControl
                  v-model="rule.label"
                  :label="__('Name')"
                  :placeholder="__('e.g. Grafana alerts')"
                />
                <FormControl
                  v-model="rule.action"
                  type="select"
                  :label="__('Then')"
                  :options="ACTIONS"
                />
              </div>
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <FormControl
                  v-model="rule.sender_pattern"
                  type="textarea"
                  :rows="2"
                  :label="__('From')"
                  :description="
                    __('Addresses or domains; a domain covers its subdomains.')
                  "
                  :placeholder="__('Any sender')"
                />
                <FormControl
                  v-model="rule.subject_pattern"
                  :label="__('Subject matches')"
                  :description="
                    __('A regular expression, not case-sensitive. Optional.')
                  "
                  :placeholder="__('Any subject')"
                />
              </div>
              <p class="text-p-xs text-ink-gray-6">
                {{ ACTION_HELP[rule.action] }}
              </p>
            </li>
          </ol>
          <p v-else class="text-p-sm text-ink-gray-6">
            {{
              __(
                "No rules: every new mail opens a ticket unless the built-in filter below catches it."
              )
            }}
          </p>
          <div>
            <Button :label="__('Add rule')" @click="addRule">
              <template #prefix>
                <LucidePlus class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
          <SettingRow
            v-slot="{ id }"
            :label="__('Ignore automated senders')"
            :description="
              __(
                'After the rules: noreply@, notifications@, mailer-daemon@ and the like.'
              )
            "
          >
            <Switch :id="id" v-model="form.ignore_automated_emails" />
          </SettingRow>
          <FormControl
            v-model="form.ignored_email_senders"
            type="textarea"
            :rows="2"
            :label="__('Always ignore mail from')"
            :description="
              __('Addresses or domains, one per line. Checked after the rules.')
            "
          />
          <SettingRow
            v-slot="{ id }"
            :label="__('Post monitor alerts to the escalation channel')"
            :description="
              __(
                'When an alert ticket opens and when its monitor resolves it. Uses the channel in Chat & Teams.'
              )
            "
          >
            <Switch :id="id" v-model="form.post_alerts_to_channel" />
          </SettingRow>
        </SettingsSection>

        <SettingsSection
          :title="__('Apply rules to open tickets')"
          :description="
            __(
              'Once, for the open tickets that came in before these rules: closes ignored mail, marks alerts and groups their repeats. Preview first; nothing changes until you apply.'
            )
          "
        >
          <SettingsPreviewAction
            :key="`cleanup-${saves}`"
            preview-method="helpdesk.api.intake.preview_cleanup"
            apply-method="helpdesk.api.intake.apply_rules_to_open_tickets"
            :preview-label="__('Preview changes')"
            :apply-label="(count) => __('Apply {0} changes', String(count))"
            :list-label="__('Changes to open tickets')"
            :rows-of="(data) => data.plan"
            :summarize="cleanupSummary"
            :unsaved="isDirty"
            @applied="settings.reload()"
          >
            <template #row="{ row }">
              <div class="flex min-w-0 flex-col gap-0.5 sm:flex-row sm:gap-3">
                <span
                  class="shrink-0 font-mono text-sm tabular-nums text-ink-gray-8"
                  >#{{ row.ticket }}</span
                >
                <span class="min-w-0 flex-1 truncate text-sm text-ink-gray-8">
                  {{ row.subject }}
                </span>
                <span class="shrink-0 text-p-sm text-ink-gray-7">
                  {{ stepLabel(row) }}
                </span>
              </div>
              <p class="truncate font-mono text-xs text-ink-gray-5">
                {{ row.raised_by }} · {{ row.rule }}
              </p>
            </template>
          </SettingsPreviewAction>
        </SettingsSection>

        <SettingsSection
          :title="__('Recently kept out')"
          :description="
            __(
              'The last mails the rules ignored or added to an open alert. Kept for 30 days.'
            )
          "
        >
          <ul
            v-if="recent.length"
            class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2"
            :aria-label="__('Recently kept out')"
          >
            <li
              v-for="entry in recent"
              :key="entry.creation + entry.subject"
              class="flex min-w-0 flex-col gap-1 px-3 py-2 sm:flex-row sm:items-center sm:gap-3"
            >
              <TaskyBadge
                :tone="LOG_TONE[entry.action]"
                :icon="LOG_ICON[entry.action]"
                :label="__(entry.action)"
              />
              <span class="min-w-0 flex-1 truncate text-sm text-ink-gray-8">
                {{ entry.subject }}
              </span>
              <span class="shrink-0 truncate font-mono text-xs text-ink-gray-5">
                {{ entry.sender }}
              </span>
              <time
                class="shrink-0 text-p-xs text-ink-gray-5"
                :datetime="entry.creation"
                :title="dateFormat(entry.creation, dateTooltipFormat)"
                >{{ timeAgo(entry.creation) }}</time
              >
            </li>
          </ul>
          <p v-else class="text-p-sm text-ink-gray-6">
            {{ __("No mail has been ignored or grouped yet.") }}
          </p>
        </SettingsSection>

        <SettingsSection
          :title="__('Routing')"
          :description="
            __(
              'After AI triage. A ticket owner assigned on arrival keeps the ticket; otherwise the team\'s round robin assigns it. What a person already set is never changed.'
            )
          "
        >
          <SettingRow
            v-slot="{ id }"
            :label="__('Apply AI triage')"
            :description="
              __(
                'Its priority while the ticket still has the default one, its ticket type, and the team below.'
              )
            "
          >
            <Switch :id="id" v-model="form.apply_triage" />
          </SettingRow>
          <template v-if="form.apply_triage">
            <SettingRow
              v-slot="{ id }"
              :label="__('Default team')"
              :description="__('For categories without a team of their own.')"
            >
              <FormControl
                :id="id"
                v-model="form.default_team"
                type="select"
                class="w-full sm:w-56"
                :options="teamOptions"
              />
            </SettingRow>
            <div
              v-if="teamWarnings.length"
              role="status"
              class="flex flex-col gap-1.5 rounded-lg border border-outline-gray-2 p-3"
            >
              <p
                v-for="warning in teamWarnings"
                :key="warning"
                class="flex items-start gap-1.5 text-p-sm text-ink-gray-8"
              >
                <LucideTriangleAlert
                  class="mt-0.5 size-4 shrink-0 text-warning"
                  aria-hidden="true"
                />
                <span>{{ warning }}</span>
              </p>
              <div>
                <Button
                  :label="__('Open Teams')"
                  variant="ghost"
                  @click="setActiveSettingsTab('Teams')"
                />
              </div>
            </div>
            <div class="flex flex-col gap-2">
              <h3 class="text-base-medium text-ink-gray-8">
                {{ __("By triage category") }}
              </h3>
              <div
                class="hidden grid-cols-[8rem_minmax(0,1fr)_minmax(0,1fr)] gap-3 px-1 text-p-xs text-ink-gray-5 sm:grid"
                aria-hidden="true"
              >
                <span>{{ __("Category") }}</span>
                <span>{{ __("Team") }}</span>
                <span>{{ __("Ticket type") }}</span>
              </div>
              <ul
                class="flex flex-col gap-2"
                :aria-label="__('By triage category')"
              >
                <li
                  v-for="route in form.routes"
                  :key="route.category"
                  class="grid grid-cols-2 items-center gap-2 sm:grid-cols-[8rem_minmax(0,1fr)_minmax(0,1fr)] sm:gap-3"
                >
                  <span
                    class="col-span-2 text-sm text-ink-gray-8 sm:col-span-1"
                  >
                    {{ __(route.category) }}
                  </span>
                  <FormControl
                    v-model="route.team"
                    type="select"
                    :aria-label="__('Team for {0}', route.category)"
                    :options="routeTeamOptions"
                  />
                  <FormControl
                    v-model="route.ticket_type"
                    type="select"
                    :aria-label="__('Ticket type for {0}', route.category)"
                    :options="typeOptions"
                  />
                </li>
              </ul>
            </div>
          </template>
        </SettingsSection>

        <SettingsSection
          :title="__('Customer detection')"
          :description="
            __(
              'A new ticket without a customer gets the one whose domain matches the sender\'s, and the sender becomes its contact. Set domains on each customer (Domain and Other Email Domains).'
            )
          "
        >
          <SettingRow
            v-slot="{ id }"
            :label="__('Match customers by email domain')"
          >
            <Switch :id="id" v-model="form.match_customer_by_domain" />
          </SettingRow>
          <FormControl
            v-if="form.match_customer_by_domain"
            v-model="form.public_email_domains"
            type="textarea"
            :rows="4"
            :label="__('Public mail domains')"
            :description="
              __(
                'One per line. Never matched to a customer, since anyone can have an address there.'
              )
            "
          />
          <div class="flex flex-col gap-2">
            <h3 class="text-base-medium text-ink-gray-8">
              {{ __("Fill customer domains from the CRM") }}
            </h3>
            <p class="max-w-prose text-p-sm text-ink-gray-6">
              {{
                __(
                  "Customers without a domain get their CRM website's. Only empty domains are filled, and never a public or already used one."
                )
              }}
            </p>
            <SettingsPreviewAction
              :key="`domains-${saves}`"
              preview-method="helpdesk.api.crm.fill_customer_domains_now"
              apply-method="helpdesk.api.crm.fill_customer_domains_now"
              :apply-params="{ apply: true }"
              :preview-label="__('Preview domains')"
              :apply-label="(count) => __('Fill {0} domains', String(count))"
              :list-label="__('Customer domains to fill')"
              :rows-of="(data) => (data.ok ? data.fill : [])"
              :summarize="domainSummary"
              :unsaved="isDirty"
            >
              <template #row="{ row }">
                <div class="flex min-w-0 items-center justify-between gap-3">
                  <span class="min-w-0 truncate text-sm text-ink-gray-8">
                    {{ row.customer }}
                  </span>
                  <span class="shrink-0 font-mono text-sm text-ink-gray-7">
                    {{ row.domain }}
                  </span>
                </div>
              </template>
            </SettingsPreviewAction>
          </div>
        </SettingsSection>

        <SettingsSection :title="__('Customer feedback')">
          <SettingRow
            v-slot="{ id }"
            :label="__('Ask for feedback when a ticket is closed')"
            :description="
              __(
                'Most tickets are closed without ever being Resolved, so the feedback email (Email Notifications) never went out. Sent once per ticket, only to customers: never for alerts or the team\'s own tickets.'
              )
            "
          >
            <Switch :id="id" v-model="form.feedback_on_close" />
          </SettingRow>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { dateFormat, dateTooltipFormat, errorText, timeAgo } from "@/utils";
import { Button, createResource, FormControl, Switch, toast } from "frappe-ui";
import { computed, ref, type Component } from "vue";
import LucideArrowDown from "~icons/lucide/arrow-down";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucideBan from "~icons/lucide/ban";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideLayers from "~icons/lucide/layers";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import SettingRow from "../SettingRow.vue";
import SettingsPreviewAction from "../SettingsPreviewAction.vue";
import SettingsSection from "../SettingsSection.vue";
import { setActiveSettingsTab } from "../settingsModal";

type Action = "Ignore" | "Alert" | "Merge into open alert";
type LogAction = "Ignored" | "Grouped" | "Resolved";

interface Rule {
  enabled: boolean;
  label: string;
  sender_pattern: string;
  subject_pattern: string;
  action: Action;
}

interface Route {
  category: string;
  team: string;
  ticket_type: string;
}

interface Team {
  name: string;
  members: number;
  disabled: boolean;
  rotation: boolean;
}

interface Form {
  rules: Rule[];
  routes: Route[];
  post_alerts_to_channel: boolean;
  apply_triage: boolean;
  default_team: string;
  match_customer_by_domain: boolean;
  public_email_domains: string;
  feedback_on_close: boolean;
  ignore_automated_emails: boolean;
  ignored_email_senders: string;
}

interface IntakeData {
  settings: Record<string, any>;
  categories: string[];
  teams: Team[];
  ticket_types: string[];
  recent: {
    action: LogAction;
    rule: string;
    sender: string;
    subject: string;
    ticket: string | null;
    creation: string;
  }[];
}

interface CleanupStep {
  ticket: string;
  subject: string;
  raised_by: string;
  rule: string;
  action: "close" | "mark_alert" | "group" | "resolve";
  target: string | null;
}

const ACTIONS: { label: string; value: Action }[] = [
  { label: __("Ignore"), value: "Ignore" },
  { label: __("Open an alert"), value: "Alert" },
  { label: __("Add to an open alert"), value: "Merge into open alert" },
];

const ACTION_HELP: Record<Action, string> = {
  Ignore: __("No ticket; the mail is listed under Recently kept out."),
  Alert: __(
    "An Alert ticket without SLA. Repeats are added to it as comments; the monitor's RESOLVED mail closes it."
  ),
  "Merge into open alert": __(
    "Only added to an open alert with the same name; never opens a ticket."
  ),
};

const LOG_TONE: Record<LogAction, Tone> = {
  Ignored: "neutral",
  Grouped: "info",
  Resolved: "success",
};

const LOG_ICON: Record<LogAction, Component> = {
  Ignored: LucideBan,
  Grouped: LucideLayers,
  Resolved: LucideCircleCheck,
};

const CHECKS = [
  "post_alerts_to_channel",
  "apply_triage",
  "match_customer_by_domain",
  "feedback_on_close",
  "ignore_automated_emails",
] as const;

const form = ref<Form | null>(null);
const initial = ref("");
// remounts the preview actions after a save, so an old preview isn't applied to new rules
const saves = ref(0);

function load(data: IntakeData) {
  const s = data.settings;
  const f = {
    ...s,
    rules: (s.rules || []).map((r: Rule) => ({
      ...r,
      enabled: Boolean(r.enabled),
      sender_pattern: r.sender_pattern || "",
      subject_pattern: r.subject_pattern || "",
    })),
    // one row per triage category; the ones without a route start empty
    routes: data.categories.map(
      (category) =>
        (s.routes || []).find((r: Route) => r.category === category) || {
          category,
          team: "",
          ticket_type: "",
        }
    ),
    default_team: s.default_team || "",
    public_email_domains: s.public_email_domains || "",
    ignored_email_senders: s.ignored_email_senders || "",
  } as Form;
  for (const key of CHECKS) (f as any)[key] = Boolean(s[key]);
  form.value = f;
  initial.value = JSON.stringify(f);
}

const settings = createResource({
  url: "helpdesk.api.intake.get_settings",
  auto: true,
  onSuccess: load,
});

const data = computed(() => settings.data as IntakeData | undefined);
const recent = computed(() => data.value?.recent ?? []);
const isDirty = computed(
  () => !!form.value && JSON.stringify(form.value) !== initial.value
);

const teamOptions = computed(() => [
  { label: __("No default team"), value: "" },
  ...(data.value?.teams ?? [])
    .filter((t) => !t.disabled)
    .map((t) => ({ label: t.name, value: t.name })),
]);
const routeTeamOptions = computed(() => [
  { label: __("Default team"), value: "" },
  ...teamOptions.value.slice(1),
]);
const typeOptions = computed(() => [
  { label: __("From the triage"), value: "" },
  ...(data.value?.ticket_types ?? [])
    .filter((t) => t !== "Alert")
    .map((t) => ({ label: t, value: t })),
]);

/** Teams tickets would be routed to that leave them unassigned. */
const teamWarnings = computed(() => {
  if (!form.value) return [];
  const routed = new Set(
    [form.value.default_team, ...form.value.routes.map((r) => r.team)].filter(
      Boolean
    )
  );
  return (data.value?.teams ?? [])
    .filter((t) => routed.has(t.name))
    .flatMap((t) => {
      if (!t.members)
        return [
          __(
            "Team {0} has no members, tickets routed there stay unassigned.",
            t.name
          ),
        ];
      if (!t.rotation)
        return [
          __(
            "Team {0}'s round robin is off, tickets routed there stay unassigned.",
            t.name
          ),
        ];
      return [];
    });
});

function addRule() {
  form.value?.rules.push({
    enabled: true,
    label: "",
    sender_pattern: "",
    subject_pattern: "",
    action: "Ignore",
  });
}

function move(index: number, by: number) {
  const rules = form.value!.rules;
  const [rule] = rules.splice(index, 1);
  rules.splice(index + by, 0, rule);
}

function stepLabel(step: CleanupStep) {
  switch (step.action) {
    case "close":
      return __("Close");
    case "mark_alert":
      return __("Mark as alert");
    case "group":
      return __("Group into #{0}", step.target);
    case "resolve":
      return __("Resolve (monitor resolved it)");
  }
}

function cleanupSummary(
  result: { plan: CleanupStep[]; done?: number; failed?: string[] },
  applied: boolean
) {
  if (!applied)
    return {
      ok: true,
      message: result.plan.length
        ? __(
            "{0} changes to open tickets. Nothing has changed yet.",
            String(result.plan.length)
          )
        : __("Nothing to change: no open ticket matches a rule."),
    };
  const failed = result.failed ?? [];
  return {
    ok: !failed.length,
    message: failed.length
      ? __(
          "{0} changes made; these failed: {1}",
          String(result.done),
          failed.join("; ")
        )
      : __("{0} changes made.", String(result.done)),
  };
}

function domainSummary(result: {
  ok: boolean;
  message: string;
  ambiguous?: unknown[];
  public?: unknown[];
  taken?: unknown[];
}) {
  if (!result.ok) return { ok: false, message: result.message };
  const skipped =
    (result.ambiguous?.length ?? 0) +
    (result.public?.length ?? 0) +
    (result.taken?.length ?? 0);
  return {
    ok: true,
    message: skipped
      ? `${result.message} ${__(
          "{0} left empty: several CRM websites, a public mail domain, or a domain another customer has.",
          String(skipped)
        )}`
      : result.message,
  };
}

const save = createResource({
  url: "helpdesk.api.intake.save_settings",
  makeParams() {
    const values: Record<string, any> = {
      ...form.value,
      rules: form.value!.rules.map((r) => ({
        ...r,
        enabled: r.enabled ? 1 : 0,
      })),
      // a category left on "default team" and "from the triage" needs no row
      routes: form.value!.routes.filter((r) => r.team || r.ticket_type),
    };
    for (const key of CHECKS) values[key] = values[key] ? 1 : 0;
    return { values };
  },
  onSuccess(saved: IntakeData) {
    settings.setData(saved);
    load(saved);
    saves.value++;
    toast.success(__("Ticket intake saved"));
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't save ticket intake")));
  },
});
</script>
