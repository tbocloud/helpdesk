<template>
  <SettingsLayoutBase
    :title="__('Follow-ups')"
    :description="
      __(
        'Reminders and escalations for tasks and tickets: who hears what, and when.'
      )
    "
    :dirty="isDirty"
    :saving="save.loading"
    :loading="!form && !settings.error"
    :error="settings.error"
    @retry="settings.reload()"
    @save="save.submit()"
  >
    <template v-if="form" #header-actions>
      <Switch v-model="form.enabled" :label="__('Enabled')" />
    </template>
    <template #content>
      <div v-if="form">
        <SettingsSection :title="__('Delivery')" :description="chatLine">
          <template #actions>
            <Button
              :label="__('Send me a test digest')"
              :loading="testDigest.loading"
              @click="testDigest.submit()"
            >
              <template #prefix>
                <LucideSend class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </template>
          <SettingRow
            v-slot="{ id }"
            :label="__('Digest times')"
            :description="
              __(
                'Each person gets one message with everything that needs them, at these times on working days (24-hour, separated by commas).'
              )
            "
          >
            <FormControl
              :id="id"
              v-model="form.digest_times"
              type="text"
              class="w-full sm:w-40"
              placeholder="09:30, 15:30"
            />
          </SettingRow>
          <SettingRow
            v-slot="{ id }"
            :label="__('Plan for today in the first digest')"
            :description="
              __(
                'The same steps as Home\'s plan for today, for everyone with open work.'
              )
            "
          >
            <Switch :id="id" v-model="form.morning_plan" />
          </SettingRow>
          <SettingRow
            v-slot="{ id }"
            :label="__('SLA breaches outside working hours')"
            :description="
              __('Everything else waits for working hours and working days.')
            "
          >
            <Switch :id="id" v-model="form.breach_pings_outside_hours" />
          </SettingRow>
          <p
            class="flex flex-wrap items-center gap-1 text-p-sm text-ink-gray-6"
          >
            {{ __("Where do messages go?") }}
            <Button
              variant="ghost"
              :label="__('Chat & Teams')"
              @click="setActiveSettingsTab('Chat & Teams')"
            >
              <template #suffix>
                <LucideArrowRight class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </p>
        </SettingsSection>

        <SettingsSection
          :title="__('Escalation ladder')"
          :description="
            __(
              'An overdue task climbs one level at each step, and each level adds people: nobody drops off. Key tasks and milestones can start one level higher.'
            )
          "
        >
          <SettingRow
            v-for="step in ladderSteps"
            :key="step.field"
            v-slot="{ id }"
            :label="step.label"
            :description="step.description"
          >
            <NumberInput
              :id="id"
              v-model="form[step.field]"
              :suffix="__('working days')"
            />
          </SettingRow>
          <SettingRow
            v-slot="{ id }"
            :label="__('Key tasks and milestones one level sooner')"
          >
            <Switch :id="id" v-model="form.key_tasks_escalate_faster" />
          </SettingRow>
        </SettingsSection>

        <SettingsSection
          :title="__('Task rules')"
          :description="
            __('Counted in working days: weekly offs and holidays are skipped.')
          "
        >
          <SettingRow
            v-for="rule in taskRules"
            :key="rule.field"
            v-slot="{ id }"
            :label="rule.label"
            :description="rule.description"
          >
            <div class="flex items-center gap-3">
              <NumberInput
                v-if="rule.amount"
                v-model="form[rule.amount]"
                :suffix="rule.unit"
                :disabled="!form[rule.field]"
                :aria-label="rule.amountLabel"
              />
              <FormControl
                v-if="rule.time"
                v-model="form.afternoon_nudge_at"
                type="time"
                class="w-28"
                :disabled="!form[rule.field]"
                :aria-label="__('Afternoon nudge from')"
              />
              <Switch :id="id" v-model="form[rule.field]" />
            </div>
          </SettingRow>
        </SettingsSection>

        <SettingsSection
          :title="__('Ticket rules')"
          :description="
            __(
              'Built on each ticket\'s SLA: warnings go to the assignee, a breach also to the team lead, and after two more working days to the Agent Managers.'
            )
          "
        >
          <SettingRow
            v-slot="{ id }"
            :label="__('SLA warnings')"
            :description="
              __(
                'At these shares of the first-reply and resolution time; the second one also tells the team lead.'
              )
            "
          >
            <div class="flex items-center gap-3">
              <NumberInput
                v-model="form.sla_first_warning"
                suffix="%"
                :disabled="!form.sla_warnings"
                :aria-label="__('First warning, percent of the SLA')"
              />
              <NumberInput
                v-model="form.sla_second_warning"
                suffix="%"
                :disabled="!form.sla_warnings"
                :aria-label="__('Second warning, percent of the SLA')"
              />
              <Switch :id="id" v-model="form.sla_warnings" />
            </div>
          </SettingRow>
          <SettingRow
            v-slot="{ id, labelledby }"
            :label="__('Support department')"
            :description="
              __(
                'Its heads are the tickets\' team lead. Without one, the Agent Managers are.'
              )
            "
          >
            <Link
              :id="id"
              :labelledby="labelledby"
              v-model="form.ticket_department"
              doctype="HD Department"
              :filters="{ is_active: 1 }"
              class="w-full sm:w-48"
              :placeholder="__('Agent Managers')"
            />
          </SettingRow>
          <SettingRow
            v-for="rule in ticketRules"
            :key="rule.field"
            v-slot="{ id }"
            :label="rule.label"
            :description="rule.description"
          >
            <div class="flex items-center gap-3">
              <NumberInput
                v-model="form[rule.amount]"
                :suffix="rule.unit"
                :disabled="!form[rule.field]"
                :aria-label="rule.amountLabel"
              />
              <Switch :id="id" v-model="form[rule.field]" />
            </div>
          </SettingRow>
        </SettingsSection>

        <SettingsSection
          :title="__('Customer follow-up')"
          :description="autoCloseLine"
        >
          <template #actions>
            <Button
              :label="__('Auto-close settings')"
              @click="setActiveSettingsTab('General')"
            />
          </template>
          <SettingRow
            v-slot="{ id }"
            :label="__('Email customers who haven\'t replied')"
            :description="
              __(
                'Once per wait, as a reply on the ticket, after the waiting days set under Ticket rules. Off: the assignee is asked to follow up instead.'
              )
            "
          >
            <Switch :id="id" v-model="form.customer_follow_up_email" />
          </SettingRow>
          <FormControl
            v-if="form.customer_follow_up_email"
            v-model="form.customer_follow_up_message"
            type="textarea"
            :rows="6"
            :label="__('Follow-up email')"
            :description="
              __(
                '{{ ticket }}, {{ subject }} and {{ customer }} are filled in. HTML is allowed.'
              )
            "
          />
        </SettingsSection>

        <SettingsSection
          :title="__('Working hours')"
          :description="
            __(
              'Follow-ups keep to the default SLA policy\'s hours and the business holidays, and skip the weekly off set under Tasks.'
            )
          "
        >
          <template #actions>
            <Button
              :label="__('SLA policies')"
              @click="setActiveSettingsTab('SLA Policies')"
            />
          </template>
          <p
            v-if="!hours?.days?.length"
            class="flex items-center gap-1.5 text-p-sm text-warning"
          >
            <LucideTriangleAlert class="size-4 shrink-0" aria-hidden="true" />
            {{
              __(
                "No default SLA policy: follow-ups go out at any time on working days."
              )
            }}
          </p>
          <dl
            v-else
            class="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm"
          >
            <template v-for="day in hours.days" :key="day.day">
              <dt class="text-ink-gray-6">{{ __(day.day) }}</dt>
              <dd class="font-mono tabular-nums text-ink-gray-8">
                {{ day.start }}–{{ day.end }}
              </dd>
            </template>
          </dl>
        </SettingsSection>

        <SettingsSection
          :title="__('Preview')"
          :description="
            __(
              'What each person would get in a digest right now, with their most pressing reason per item.'
            )
          "
        >
          <template #actions>
            <Button
              variant="ghost"
              :label="__('Refresh')"
              :loading="preview.loading"
              @click="preview.reload()"
            >
              <template #prefix>
                <LucideRefreshCw class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </template>
          <p v-if="preview.error" class="text-p-sm text-danger" role="alert">
            {{ __("Couldn't load the preview.") }}
            <Button
              variant="ghost"
              :label="__('Try again')"
              @click="preview.reload()"
            />
          </p>
          <div v-else-if="!people" class="flex flex-col gap-2">
            <div
              v-for="i in 3"
              :key="i"
              class="h-10 animate-pulse rounded-md bg-surface-gray-2"
            />
          </div>
          <p
            v-else-if="!people.length"
            class="flex items-center gap-1.5 text-p-sm text-ink-gray-6"
          >
            <LucideCircleCheck
              class="size-4 shrink-0 text-success"
              aria-hidden="true"
            />
            {{ __("Nothing needs anyone right now.") }}
          </p>
          <ul
            v-else
            role="list"
            class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2"
          >
            <li v-for="person in people" :key="person.user">
              <details class="group">
                <summary
                  class="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                >
                  <LucideChevronRight
                    class="size-4 shrink-0 text-ink-gray-5 transition-transform group-open:rotate-90"
                    aria-hidden="true"
                  />
                  <span
                    class="min-w-0 flex-1 truncate text-base text-ink-gray-9"
                  >
                    {{ person.full_name }}
                  </span>
                  <span class="font-mono text-sm tabular-nums text-ink-gray-6">
                    {{ person.items.length }}
                  </span>
                </summary>
                <ul role="list" class="flex flex-col gap-2 px-3 pb-3 ps-9">
                  <li
                    v-for="item in person.items"
                    :key="`${item.doctype}:${item.name}`"
                    class="flex flex-col gap-1 text-p-sm text-ink-gray-7"
                  >
                    <span class="flex flex-wrap items-center gap-1.5">
                      <TaskyBadge
                        :tone="SEVERITY_TONES[item.severity]"
                        :label="item.rule_label"
                      />
                      <EscalationBadge :level="item.level" />
                    </span>
                    <span>{{ item.text }}</span>
                  </li>
                </ul>
              </details>
            </li>
          </ul>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import EscalationBadge from "@/components/EscalationBadge.vue";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { Button, createResource, FormControl, Switch, toast } from "frappe-ui";
import { computed, ref } from "vue";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSend from "~icons/lucide/send";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import SettingRow from "../SettingRow.vue";
import SettingsSection from "../SettingsSection.vue";
import { setActiveSettingsTab } from "../settingsModal";
import NumberInput from "./NumberInput.vue";

type Form = Record<string, any>;

interface PreviewItem {
  doctype: string;
  name: string;
  text: string;
  rule_label: string;
  severity: "breach" | "escalated" | "overdue" | "due" | "waiting";
  level: number;
}

interface PreviewPerson {
  user: string;
  full_name: string;
  items: PreviewItem[];
}

interface SettingsData {
  settings: Form;
  working_hours: {
    sla: string | null;
    days: { day: string; start: string; end: string }[];
  };
  auto_close: { enabled: boolean; days: number; status: string };
  chat: { enabled: boolean; platform: string; direct_messages: boolean };
}

// Check fields come as 0/1 and go back the same way
const CHECKS = [
  "enabled",
  "morning_plan",
  "breach_pings_outside_hours",
  "key_tasks_escalate_faster",
  "due_tomorrow",
  "due_today",
  "overdue",
  "untouched",
  "review",
  "hold",
  "no_due_date",
  "blocked",
  "sla_warnings",
  "unassigned",
  "customer_replied",
  "awaiting_customer",
  "customer_follow_up_email",
];

const SEVERITY_TONES: Record<PreviewItem["severity"], Tone> = {
  breach: "danger",
  escalated: "danger",
  overdue: "danger",
  due: "info",
  waiting: "neutral",
};

const days = __("working days");

const ladderSteps = [
  {
    field: "ladder_l1_days",
    label: __("Lead"),
    description: __("The assigner and the project lead join the assignee."),
  },
  {
    field: "ladder_l2_days",
    label: __("Head"),
    description: __(
      "The project coordinators and the department heads join (the project managers when it has no department)."
    ),
  },
  {
    field: "ladder_l3_days",
    label: __("Managers"),
    description: __("The Agent Managers join."),
  },
];

const taskRules = [
  {
    field: "due_tomorrow",
    label: __("Due next working day"),
    description: __("A reminder to the assignee."),
  },
  {
    field: "due_today",
    label: __("Due today, not started"),
    description: __(
      "In the morning, then again from this time if there's still no progress or timer."
    ),
    time: true,
  },
  {
    field: "overdue",
    label: __("Overdue"),
    description: __(
      "Every working day until it's completed, cancelled or put on hold, up the ladder above."
    ),
  },
  {
    field: "untouched",
    label: __("Assigned, untouched"),
    description: __(
      "No status change, timer or comment: the assignee, then a day later the assigner too."
    ),
    amount: "untouched_days",
    unit: days,
    amountLabel: __("Untouched for, working days"),
  },
  {
    field: "review",
    label: __("Waiting for review"),
    description: __("The reviewer, then a day later the lead too."),
    amount: "review_days",
    unit: days,
    amountLabel: __("In review for, working days"),
  },
  {
    field: "hold",
    label: __("On hold"),
    description: __(
      "Whoever held it, to resume or update the note; waiting on the customer also asks the assignee to follow up. At twice this, the lead too."
    ),
    amount: "hold_days",
    unit: days,
    amountLabel: __("On hold for, working days"),
  },
  {
    field: "no_due_date",
    label: __("No due date"),
    description: __("The assigner, or the lead, is asked to set one."),
    amount: "no_due_date_days",
    unit: days,
    amountLabel: __("Without a due date for, working days"),
  },
  {
    field: "blocked",
    label: __("Blocking an overdue task"),
    description: __(
      "Someone waits on a task that is overdue: its assignee hears who is waiting."
    ),
  },
];

const ticketRules = [
  {
    field: "unassigned",
    label: __("Unassigned"),
    description: __("Its team and the Agent Managers."),
    amount: "unassigned_minutes",
    unit: __("working minutes"),
    amountLabel: __("Unassigned for, working minutes"),
  },
  {
    field: "customer_replied",
    label: __("Customer replied, no answer"),
    description: __("The assignee, then at twice this the team lead too."),
    amount: "customer_replied_hours",
    unit: __("working hours"),
    amountLabel: __("Unanswered for, working hours"),
  },
  {
    field: "awaiting_customer",
    label: __("Waiting on the customer"),
    description: __(
      "Replied or paused with no answer from them: the follow-up email below, or the assignee is asked to follow up."
    ),
    amount: "awaiting_customer_days",
    unit: days,
    amountLabel: __("Waiting for, working days"),
  },
];

const form = ref<Form | null>(null);
const initial = ref("");

function toForm(values: Form): Form {
  const f: Form = { ...values };
  for (const key of CHECKS) f[key] = Boolean(f[key]);
  f.afternoon_nudge_at = String(f.afternoon_nudge_at || "14:00").slice(0, 5);
  return f;
}

const settings = createResource({
  url: "helpdesk.api.follow_ups.get_settings",
  auto: true,
  onSuccess(data: SettingsData) {
    form.value = toForm(data.settings);
    initial.value = JSON.stringify(form.value);
  },
});

const data = computed(() => settings.data as SettingsData | undefined);
const hours = computed(() => data.value?.working_hours);

const chatLine = computed(() => {
  const chat = data.value?.chat;
  if (!chat?.enabled)
    return __(
      "Chat isn't switched on (Chat & Teams), so digests and pings go by email."
    );
  if (!chat.direct_messages)
    return __(
      "{0} is on, but without direct messages: digests and pings go by email.",
      chat.platform
    );
  return __("Digests and pings go to people in {0}.", chat.platform);
});

const autoCloseLine = computed(() => {
  const a = data.value?.auto_close;
  if (!a?.enabled)
    return __(
      "Auto-close is off (General): after the follow-up email, the assignee is asked to close or call."
    );
  return __(
    "Auto-close is on (General): tickets in {0} close {1} days after the last email, the follow-up included.",
    a.status,
    String(a.days)
  );
});

const isDirty = computed(
  () => !!form.value && JSON.stringify(form.value) !== initial.value
);

const save = createResource({
  url: "helpdesk.api.follow_ups.save_settings",
  makeParams() {
    const values: Form = { ...form.value };
    for (const key of CHECKS) values[key] = values[key] ? 1 : 0;
    return { values };
  },
  onSuccess(saved: Form) {
    form.value = toForm(saved);
    initial.value = JSON.stringify(form.value);
    toast.success(__("Follow-up settings saved"));
    preview.reload();
  },
  onError(e: { messages?: string[] }) {
    toast.error(e.messages?.[0] || __("Couldn't save the follow-up settings"));
  },
});

const testDigest = createResource({
  url: "helpdesk.api.follow_ups.send_test_digest",
  onSuccess(result: { via: string; items: number }) {
    toast.success(
      result.via === "chat"
        ? __(
            "Test digest sent to you in chat ({0} items)",
            String(result.items)
          )
        : __("Test digest emailed to you ({0} items)", String(result.items))
    );
  },
  onError(e: { messages?: string[] }) {
    toast.error(e.messages?.[0] || __("Couldn't send the test digest"));
  },
});

const preview = createResource({
  url: "helpdesk.api.follow_ups.get_preview",
  auto: true,
});
const people = computed(() => preview.data as PreviewPerson[] | undefined);
</script>
