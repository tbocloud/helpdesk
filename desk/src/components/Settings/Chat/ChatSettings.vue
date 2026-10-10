<template>
  <SettingsLayoutBase
    :title="__('Chat & Teams')"
    :description="
      __(
        'Reminders, mentions and escalations go to Microsoft Teams or Slack instead of email. Emails to customers are not affected.'
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
        <SettingsSection :title="__('Delivery')">
          <SettingRow v-slot="{ id }" :label="__('Platform')">
            <FormControl
              :id="id"
              v-model="form.platform"
              type="select"
              class="w-full sm:w-48"
              :options="[TEAMS, SLACK]"
            />
          </SettingRow>
          <SettingRow
            v-slot="{ id }"
            :label="__('Email people who can\'t be reached in chat')"
            :description="
              form.platform === SLACK
                ? __('People whose email isn\'t in the Slack workspace.')
                : __(
                    'When there\'s no Direct Message Workflow URL, or the workflow fails.'
                  )
            "
          >
            <Switch :id="id" v-model="form.email_when_unreachable" />
          </SettingRow>
        </SettingsSection>

        <SettingsSection
          v-if="form.platform === TEAMS"
          :title="__('Microsoft Teams')"
          :description="
            __(
              'Two Teams Workflows, no Azure app: one messages each person, one posts escalations to a channel. How to create them is below.'
            )
          "
        >
          <SecretField
            v-model="edits.teams_direct_webhook"
            :label="LABELS.teams_direct_webhook"
            :description="
              __(
                'Reminders, mentions and digests, to each person\'s chat with the Flow bot. Without it, they go by email.'
              )
            "
            :status="secrets.teams_direct_webhook"
            :error="fieldErrors.teams_direct_webhook"
            placeholder="https://…logic.azure.com/…&sig=…"
            removable
          >
            <SendTest
              :key="`direct-${saves}`"
              target="direct"
              :label="__('Send me a test')"
              :unsaved="isDirty"
            />
          </SecretField>
          <SecretField
            v-model="edits.teams_channel_webhook"
            :label="LABELS.teams_channel_webhook"
            :description="
              __(
                'Optional. Escalations and error alerts, posted once to the team\'s channel.'
              )
            "
            :status="secrets.teams_channel_webhook"
            :error="fieldErrors.teams_channel_webhook"
            placeholder="https://…powerplatform.com/…&sig=…"
            removable
          >
            <SendTest
              :key="`channel-${saves}`"
              target="channel"
              :label="__('Send a test to the channel')"
              :unsaved="isDirty"
            />
          </SecretField>
        </SettingsSection>

        <SettingsSection
          v-else
          :title="__('Slack')"
          :description="
            __(
              'A Slack app with the chat:write, users:read and users:read.email scopes. People are matched by email.'
            )
          "
        >
          <SecretField
            v-model="edits.slack_bot_token"
            :label="LABELS.slack_bot_token"
            :description="
              __(
                'From your Slack app (OAuth & Permissions), starts with xoxb-.'
              )
            "
            :status="secrets.slack_bot_token"
            :error="fieldErrors.slack_bot_token"
            type="password"
            placeholder="xoxb-…"
          >
            <SendTest
              :key="`direct-${saves}`"
              target="direct"
              :label="__('Send me a test')"
              :unsaved="isDirty"
            />
          </SecretField>
          <div class="flex flex-col items-start gap-2">
            <FormControl
              v-model="form.slack_escalation_channel"
              class="w-full sm:w-64"
              :label="__('Escalation Channel ID')"
              :description="
                __(
                  'Optional, e.g. C0123ABCD, under the channel\'s details in Slack. Invite the app to the channel.'
                )
              "
              placeholder="C0123ABCD"
            />
            <SendTest
              :key="`channel-${saves}`"
              target="channel"
              :label="__('Send a test to the channel')"
              :unsaved="isDirty"
            />
          </div>
        </SettingsSection>

        <SettingsSection
          :title="__('Error alerts')"
          :description="
            __(
              'Every 10 minutes, new errors in the hub are grouped by title and posted once to the escalation channel, so problems are seen before customers report them.'
            )
          "
        >
          <SettingRow
            v-slot="{ id }"
            :label="__('Post hub errors to the escalation channel')"
          >
            <Switch :id="id" v-model="form.post_error_alerts" />
          </SettingRow>
          <FormControl
            v-if="form.post_error_alerts"
            v-model="form.ignored_error_titles"
            type="textarea"
            :rows="3"
            :label="__('Don\'t post errors whose title contains')"
            :description="
              __(
                'One per line, not case-sensitive. For known, harmless errors.'
              )
            "
          />
        </SettingsSection>

        <SettingsSection
          v-if="lastProblem"
          :title="__('Last delivery problem')"
        >
          <p class="flex items-start gap-1.5 text-p-sm text-ink-gray-7">
            <LucideTriangleAlert
              class="mt-0.5 size-4 shrink-0 text-warning"
              aria-hidden="true"
            />
            <span>
              {{ lastProblem.title }},
              <time
                :datetime="lastProblem.at"
                :title="dateFormat(lastProblem.at, dateTooltipFormat)"
              >
                {{ timeAgo(lastProblem.at) }}</time
              >.
              {{
                __(
                  "Send a test message above to see the exact error and how to fix it."
                )
              }}
            </span>
          </p>
        </SettingsSection>

        <SettingsSection
          v-if="form.platform === TEAMS"
          :title="__('Creating the Teams workflows')"
        >
          <div class="flex flex-col gap-2">
            <h3 class="text-base-medium text-ink-gray-8">
              {{ __("Direct messages") }}
            </h3>
            <ol
              class="flex list-decimal flex-col gap-1 ps-5 text-p-sm text-ink-gray-7"
            >
              <li>
                {{
                  __(
                    'In Teams, open Workflows and start from the template "Post to a chat when a webhook request is received".'
                  )
                }}
              </li>
              <li>
                {{
                  __(
                    'On the trigger, set "Who can trigger the flow" to Anyone.'
                  )
                }}
              </li>
              <li>
                {{
                  __(
                    "In the step that posts the card: post as Flow bot, post in Chat with Flow bot, and set Recipient to the expression"
                  )
                }}
                <code class="font-mono text-ink-gray-8"
                  >triggerBody()?['recipient']</code
                >.
              </li>
              <li>
                {{
                  __(
                    "Save, open the trigger again and copy its HTTP URL (it ends with &sig=…). Paste it in Direct Message Workflow URL."
                  )
                }}
              </li>
            </ol>
          </div>
          <div class="flex flex-col gap-2">
            <h3 class="text-base-medium text-ink-gray-8">
              {{ __("Escalation channel") }}
            </h3>
            <p class="text-p-sm text-ink-gray-7">
              {{
                __(
                  'Start from the template "Post to a channel when a webhook request is received", pick the team and channel, save, and paste its HTTP URL in Escalation Channel Workflow URL.'
                )
              }}
            </p>
          </div>
          <details class="group rounded-lg border border-outline-gray-2">
            <summary
              class="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-base text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >
              <LucideChevronRight
                class="size-4 shrink-0 text-ink-gray-5 transition-transform group-open:rotate-90"
                aria-hidden="true"
              />
              {{ __("What TBO Support sends") }}
            </summary>
            <div class="flex flex-col gap-2 px-3 pb-3">
              <p class="text-p-sm text-ink-gray-6">
                {{
                  __(
                    "A JSON POST with one Adaptive Card in attachments; the templates' \"Apply to each\" loop posts it. Only the direct-message workflow gets recipient, the person's email in TBO Support."
                  )
                }}
              </p>
              <pre
                class="overflow-x-auto rounded bg-surface-gray-1 p-3 font-mono text-xs text-ink-gray-8"
                >{{ PAYLOAD_SAMPLE }}</pre
              >
            </div>
          </details>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { __ } from "@/translation";
import { dateFormat, dateTooltipFormat, timeAgo } from "@/utils";
import { createResource, FormControl, Switch, toast } from "frappe-ui";
import { computed, reactive, ref } from "vue";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import SettingRow from "../SettingRow.vue";
import SettingsSection from "../SettingsSection.vue";
import SecretField, {
  type SecretEdit,
  type SecretStatus,
} from "./SecretField.vue";
import SendTest from "./SendTest.vue";

const TEAMS = "Microsoft Teams";
const SLACK = "Slack";

// the shape chat_notifications.teams_message posts, plus recipient for direct messages
const PAYLOAD_SAMPLE = JSON.stringify(
  {
    recipient: "person@example.com",
    type: "message",
    attachments: [
      {
        contentType: "application/vnd.microsoft.card.adaptive",
        contentUrl: null,
        content: {
          $schema: "http://adaptivecards.io/schemas/adaptive-card.json",
          type: "AdaptiveCard",
          version: "1.4",
          body: [
            {
              type: "TextBlock",
              text: "Due tomorrow: Go-live checklist",
              wrap: true,
            },
          ],
          actions: [
            {
              type: "Action.OpenUrl",
              title: "Open in TBO Support",
              url: "https://…/helpdesk/…",
            },
          ],
        },
      },
    ],
  },
  null,
  2
);

const SECRETS = [
  "slack_bot_token",
  "teams_direct_webhook",
  "teams_channel_webhook",
] as const;
type Secret = typeof SECRETS[number];

// Check fields come as 0/1 and go back the same way
const CHECKS = ["enabled", "email_when_unreachable", "post_error_alerts"];

interface SettingsData {
  settings: Record<string, any>;
  secrets: Record<Secret, SecretStatus>;
  last_problem: { title: string; at: string } | null;
}

const form = ref<Record<string, any> | null>(null);
const initial = ref("");
const edits = reactive({} as Record<Secret, SecretEdit>);
const fieldErrors = reactive({} as Partial<Record<Secret, string>>);
// remounts the test buttons after a save, so an old result isn't shown for new settings
const saves = ref(0);

function load(data: SettingsData) {
  const f = { ...data.settings };
  for (const key of CHECKS) f[key] = Boolean(f[key]);
  form.value = f;
  initial.value = JSON.stringify(f);
  for (const key of SECRETS) {
    edits[key] = { mode: "keep", value: "" };
    delete fieldErrors[key];
  }
}

const settings = createResource({
  url: "helpdesk.api.chat_settings.get_settings",
  auto: true,
  onSuccess: load,
});

const data = computed(() => settings.data as SettingsData | undefined);
const secrets = computed(
  () => data.value?.secrets ?? ({} as Record<Secret, SecretStatus>)
);
const lastProblem = computed(() => data.value?.last_problem);

/** What a secret's edit sends: a new value, "" to remove it, or nothing. */
function secretParam(key: Secret): string | undefined {
  const edit = edits[key];
  if (edit?.mode === "remove") return "";
  if (edit?.mode === "replace" && edit.value.trim()) return edit.value.trim();
  return undefined;
}

const isDirty = computed(
  () =>
    !!form.value &&
    (JSON.stringify(form.value) !== initial.value ||
      SECRETS.some((key) => secretParam(key) !== undefined))
);

const LABELS: Record<Secret, string> = {
  slack_bot_token: __("Bot Token"),
  teams_direct_webhook: __("Direct Message Workflow URL"),
  teams_channel_webhook: __("Escalation Channel Workflow URL"),
};

const save = createResource({
  url: "helpdesk.api.chat_settings.save_settings",
  makeParams() {
    const values: Record<string, any> = { ...form.value };
    for (const key of CHECKS) values[key] = values[key] ? 1 : 0;
    for (const key of SECRETS) {
      const value = secretParam(key);
      if (value !== undefined) values[key] = value;
    }
    return { values };
  },
  onSuccess(saved: SettingsData) {
    settings.setData(saved);
    load(saved);
    saves.value++;
    toast.success(__("Chat settings saved"));
  },
  onError(e: { messages?: string[] }) {
    const message = e.messages?.[0] || __("Couldn't save the chat settings");
    // the doctype names the field first: "Direct Message Workflow URL: …"
    for (const key of SECRETS)
      fieldErrors[key] = message.startsWith(`${LABELS[key]}:`)
        ? message
        : undefined;
    toast.error(message);
  },
});
</script>
