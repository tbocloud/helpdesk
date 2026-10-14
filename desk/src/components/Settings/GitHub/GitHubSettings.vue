<template>
  <SettingsLayoutBase
    :title="__('GitHub')"
    :description="
      __(
        'Pull requests move the tasks they name, and the org merge bot runs when a PR may be ready to merge.'
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
        <SettingsSection
          :title="__('Webhook')"
          :description="
            __(
              'Add it at organization level in tbocloud and teambackoffice. While the sync is off, every delivery is refused.'
            )
          "
        >
          <div class="flex flex-col gap-1">
            <span :id="payloadLabelId" class="text-base-medium text-ink-gray-8">
              {{ __("Payload URL") }}
            </span>
            <div class="flex flex-wrap items-center gap-2">
              <code
                :aria-labelledby="payloadLabelId"
                class="min-w-0 flex-1 break-all rounded border border-outline-gray-2 bg-surface-gray-1 px-2 py-1.5 font-mono text-sm text-ink-gray-8"
              >
                {{ data?.webhook_url }}
              </code>
              <Button
                :label="__('Copy')"
                @click="
                  copyToClipboard(data?.webhook_url, __('Payload URL copied'))
                "
              >
                <template #prefix>
                  <LucideCopy class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </div>
            <p class="text-p-sm text-ink-gray-6">
              {{ __("Content type") }}
              <code class="font-mono text-ink-gray-8">application/json</code>.
              {{ __("Events:") }} {{ EVENTS.join(", ") }}.
            </p>
          </div>
          <SecretField
            v-model="edits.webhook_secret"
            :label="LABELS.webhook_secret"
            :description="
              __(
                'The same value as the webhook\'s Secret in GitHub. Unsigned or wrongly signed deliveries are refused.'
              )
            "
            :status="secrets.webhook_secret"
            :error="fieldErrors.webhook_secret"
            type="password"
            removable
          />
        </SettingsSection>

        <SettingsSection
          :title="__('Task sync')"
          :description="
            __(
              'A PR that names a task (TASK-2026-00012) in its title, description or branch moves that task.'
            )
          "
        >
          <div class="flex flex-col gap-1.5">
            <FormControl
              v-model="form.allowed_repos"
              type="textarea"
              :rows="3"
              :label="LABELS.allowed_repos"
              :description="
                __(
                  'One per line: owner/repo, or owner/* for all of an owner\'s repositories. Deliveries from others are logged as Ignored.'
                )
              "
              placeholder="tbocloud/*"
            />
            <ErrorMessage
              v-if="fieldErrors.allowed_repos"
              role="alert"
              :message="fieldErrors.allowed_repos"
            />
          </div>
          <SettingRow
            v-slot="{ id }"
            :label="__('Complete the task when a closing PR is merged')"
            :description="
              __(
                'For PRs that say “Closes TASK-…”. Projects that want review first send the task to review instead.'
              )
            "
          >
            <Switch :id="id" v-model="form.complete_on_merge" />
          </SettingRow>
          <SettingRow
            v-slot="{ id, labelledby }"
            :label="__('Project for PRs without a task')"
            :description="
              __(
                'A PR that names no task gets a new task here. Empty: System and Agent Managers are told instead.'
              )
            "
          >
            <Link
              :id="id"
              :labelledby="labelledby"
              v-model="form.unlinked_pr_project"
              doctype="Project"
              class="w-full sm:w-56"
              :placeholder="__('Tell the managers')"
            />
          </SettingRow>
          <SecretField
            v-model="edits.github_token"
            :label="LABELS.github_token"
            :description="
              __(
                'Optional. Lets TBO Support ask a PR for its task number and read why a PR was closed: needs read and write on pull requests and issues.'
              )
            "
            :status="secrets.github_token"
            :error="fieldErrors.github_token"
            type="password"
            placeholder="github_pat_…"
            removable
          >
            <SettingsAction
              v-if="secrets.github_token?.set"
              :key="`github-${saves}`"
              :method="TEST_TOKEN"
              :params="{ field: 'github_token' }"
              :label="__('Test GitHub token')"
              :icon="LucideKeyRound"
              :unsaved="isDirty"
            />
          </SecretField>
        </SettingsSection>

        <SettingsSection
          :title="__('Org merge bot')"
          :description="
            __(
              'The bot merges PRs in both organisations that CodeRabbit approved and whose checks are green. TBO Support asks for a run when that may have happened, and every 10 minutes, at most once per 2 minutes.'
            )
          "
        >
          <SettingRow
            v-slot="{ id }"
            :label="__('Trigger the org merge bot')"
            :description="
              __(
                'Needs the organization webhook to send Pull request reviews, Check suites and Workflow runs.'
              )
            "
          >
            <Switch :id="id" v-model="form.trigger_merge_bot" />
          </SettingRow>
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="flex min-w-0 flex-col gap-1.5">
              <FormControl
                v-model="form.merge_bot_repo"
                :label="LABELS.merge_bot_repo"
                placeholder="tbocloud/ai-review"
              />
              <ErrorMessage
                v-if="fieldErrors.merge_bot_repo"
                role="alert"
                :message="fieldErrors.merge_bot_repo"
              />
            </div>
            <div class="flex min-w-0 flex-col gap-1.5">
              <FormControl
                v-model="form.merge_bot_workflow"
                :label="LABELS.merge_bot_workflow"
                :description="
                  __('The file name; run on main with dry_run off.')
                "
                placeholder="merge-bot.yml"
              />
              <ErrorMessage
                v-if="fieldErrors.merge_bot_workflow"
                role="alert"
                :message="fieldErrors.merge_bot_workflow"
              />
            </div>
          </div>
          <SecretField
            v-model="edits.merge_bot_token"
            :label="LABELS.merge_bot_token"
            :description="
              __(
                'Optional. A fine-grained token with Actions: Read and write on the merge bot repository only. Empty: the GitHub token is used.'
              )
            "
            :status="secrets.merge_bot_token"
            :error="fieldErrors.merge_bot_token"
            type="password"
            placeholder="github_pat_…"
            removable
          >
            <SettingsAction
              v-if="secrets.merge_bot_token?.set"
              :key="`merge-bot-${saves}`"
              :method="TEST_TOKEN"
              :params="{ field: 'merge_bot_token' }"
              :label="__('Test merge bot token')"
              :icon="LucideKeyRound"
              :unsaved="isDirty"
            />
          </SecretField>

          <div class="flex flex-col gap-3">
            <dl
              class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-p-sm"
            >
              <dt class="text-ink-gray-6">{{ __("Last run requested") }}</dt>
              <dd class="text-ink-gray-8">
                <time
                  v-if="statusData?.last_dispatch"
                  :datetime="statusData.last_dispatch"
                  :title="
                    dateFormat(statusData.last_dispatch, dateTooltipFormat)
                  "
                  >{{ timeAgo(statusData.last_dispatch) }}</time
                >
                <template v-else>{{ __("Never") }}</template>
              </dd>
              <dt class="text-ink-gray-6">{{ __("Last result") }}</dt>
              <dd class="flex items-start gap-1.5" :class="INK[resultTone]">
                <component
                  :is="
                    resultTone === 'success'
                      ? LucideCircleCheck
                      : LucideCircleAlert
                  "
                  v-if="resultTone !== 'neutral'"
                  class="mt-0.5 size-4 shrink-0"
                  aria-hidden="true"
                />
                <span>{{ statusData?.last_result || __("None yet") }}</span>
              </dd>
            </dl>
            <SettingsAction
              :key="`run-${saves}`"
              method="helpdesk.api.github_settings.request_merge_bot_run"
              :label="__('Request a merge bot run now')"
              :icon="LucidePlay"
              :unsaved="isDirty"
              @done="status.reload()"
            />
          </div>
        </SettingsSection>

        <SettingsSection :title="__('Last webhook delivery')">
          <p v-if="status.error" class="text-p-sm text-ink-gray-6">
            {{ __("Couldn't load the delivery log.") }}
            <Button
              variant="ghost"
              :label="__('Try again')"
              @click="status.reload()"
            />
          </p>
          <p v-else-if="!lastDelivery" class="text-p-sm text-ink-gray-6">
            {{
              __(
                "None yet. Once the webhook is added, GitHub's ping and the next PR event show here."
              )
            }}
          </p>
          <dl
            v-else
            class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-p-sm"
          >
            <dt class="text-ink-gray-6">{{ __("Received") }}</dt>
            <dd class="text-ink-gray-8">
              <time
                :datetime="lastDelivery.at"
                :title="dateFormat(lastDelivery.at, dateTooltipFormat)"
                >{{ timeAgo(lastDelivery.at) }}</time
              >
            </dd>
            <dt class="text-ink-gray-6">{{ __("Event") }}</dt>
            <dd class="break-words font-mono text-ink-gray-8">
              {{ lastDelivery.event
              }}{{ lastDelivery.action ? ` · ${lastDelivery.action}` : "" }}
              <span v-if="lastDelivery.repo" class="text-ink-gray-6">
                · {{ lastDelivery.repo }}
              </span>
            </dd>
            <dt class="text-ink-gray-6">{{ __("Status") }}</dt>
            <dd>
              <TaskyBadge
                :label="lastDelivery.status"
                :tone="DELIVERY_TONES[lastDelivery.status]"
              />
            </dd>
          </dl>
        </SettingsSection>

        <SettingsSection :title="__('Setting up GitHub')">
          <details class="group rounded-lg border border-outline-gray-2">
            <summary :class="SUMMARY_CLASS">
              <LucideChevronRight :class="CHEVRON_CLASS" aria-hidden="true" />
              {{ __("The organization webhook") }}
            </summary>
            <ol :class="STEPS_CLASS">
              <li>
                {{
                  __(
                    "In GitHub, open the organization's Settings → Webhooks → Add webhook. Do this in both tbocloud and teambackoffice."
                  )
                }}
              </li>
              <li>
                {{
                  __(
                    "Paste the Payload URL above, set Content type to application/json, and enter the Webhook Secret saved here."
                  )
                }}
              </li>
              <li>
                {{
                  __(
                    "Choose Let me select individual events and tick Pull requests, Pull request reviews, Check suites and Workflow runs."
                  )
                }}
              </li>
              <li>
                {{
                  __(
                    "Save. GitHub sends a ping; remove any older repository webhook to this hub so events don't arrive twice."
                  )
                }}
              </li>
            </ol>
          </details>
          <details class="group rounded-lg border border-outline-gray-2">
            <summary :class="SUMMARY_CLASS">
              <LucideChevronRight :class="CHEVRON_CLASS" aria-hidden="true" />
              {{ __("A fine-grained token for the merge bot") }}
            </summary>
            <ol :class="STEPS_CLASS">
              <li>
                {{
                  __(
                    "In GitHub, open your Settings → Developer settings → Fine-grained tokens → Generate new token."
                  )
                }}
              </li>
              <li>
                {{
                  __(
                    "Resource owner: tbocloud. Repository access: Only select repositories, the merge bot repository."
                  )
                }}
              </li>
              <li>
                {{
                  __(
                    "Repository permissions: Actions, Read and write. Nothing else is needed."
                  )
                }}
              </li>
              <li>
                {{
                  __(
                    "Generate it, paste it in Merge bot token, save, then test it."
                  )
                }}
              </li>
            </ol>
          </details>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { INK, type Tone } from "@/components/tone";
import { __ } from "@/translation";
import {
  copyToClipboard,
  dateFormat,
  dateTooltipFormat,
  timeAgo,
} from "@/utils";
import {
  Button,
  createResource,
  ErrorMessage,
  FormControl,
  Switch,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId } from "vue";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCopy from "~icons/lucide/copy";
import LucideKeyRound from "~icons/lucide/key-round";
import LucidePlay from "~icons/lucide/play";
import SecretField, {
  type SecretEdit,
  type SecretStatus,
} from "../SecretField.vue";
import { secretValue } from "../secretEdit";
import SettingRow from "../SettingRow.vue";
import SettingsAction from "../SettingsAction.vue";
import SettingsSection from "../SettingsSection.vue";

const TEST_TOKEN = "helpdesk.api.github_settings.test_token";
const EVENTS = [
  __("Pull requests"),
  __("Pull request reviews"),
  __("Check suites"),
  __("Workflow runs"),
];
const DELIVERY_TONES: Record<string, Tone> = {
  Processed: "success",
  Failed: "danger",
};
const SUMMARY_CLASS =
  "flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-base text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4";
const CHEVRON_CLASS =
  "size-4 shrink-0 text-ink-gray-5 transition-transform group-open:rotate-90";
const STEPS_CLASS =
  "flex list-decimal flex-col gap-1 px-3 pb-3 ps-8 text-p-sm text-ink-gray-7";

const SECRETS = ["webhook_secret", "github_token", "merge_bot_token"] as const;
type Secret = typeof SECRETS[number];
type ErrorField =
  | Secret
  | "allowed_repos"
  | "merge_bot_repo"
  | "merge_bot_workflow";

// Check fields come as 0/1 and go back the same way
const CHECKS = ["enabled", "complete_on_merge", "trigger_merge_bot"];

// HDGitHubSettings.validate starts its messages with these labels
const LABELS: Record<ErrorField, string> = {
  webhook_secret: __("Webhook Secret"),
  github_token: __("GitHub Token"),
  merge_bot_token: __("Merge bot token"),
  allowed_repos: __("Allowed Repositories"),
  merge_bot_repo: __("Merge bot repository"),
  merge_bot_workflow: __("Merge bot workflow"),
};

interface SettingsData {
  settings: Record<string, any>;
  secrets: Record<Secret, SecretStatus>;
  webhook_url: string;
}

interface StatusData {
  last_dispatch: string | null;
  last_result: string | null;
  last_outcome: "Dispatched" | "Failed" | "" | null;
  last_delivery: {
    at: string;
    event: string;
    action: string;
    repo: string;
    status: string;
  } | null;
}

const payloadLabelId = `payload-${useId()}`;
const form = ref<Record<string, any> | null>(null);
const initial = ref("");
const edits = reactive({} as Record<Secret, SecretEdit>);
const fieldErrors = reactive({} as Partial<Record<ErrorField, string>>);
// remounts the action buttons after a save, so an old result isn't shown for new settings
const saves = ref(0);

function load(data: SettingsData) {
  const f = { ...data.settings };
  for (const key of CHECKS) f[key] = Boolean(f[key]);
  form.value = f;
  initial.value = JSON.stringify(f);
  for (const key of SECRETS) edits[key] = { mode: "keep", value: "" };
  for (const key of Object.keys(LABELS)) delete fieldErrors[key];
}

const settings = createResource({
  url: "helpdesk.api.github_settings.get_settings",
  auto: true,
  onSuccess: load,
});

const status = createResource({
  url: "helpdesk.api.github_settings.get_status",
  auto: true,
});

const data = computed(() => settings.data as SettingsData | undefined);
const secrets = computed(
  () => data.value?.secrets ?? ({} as Record<Secret, SecretStatus>)
);
const statusData = computed(() => status.data as StatusData | undefined);
const lastDelivery = computed(() => statusData.value?.last_delivery);
const OUTCOME_TONES: Record<string, Tone> = {
  Dispatched: "success",
  Failed: "danger",
};
const resultTone = computed<Tone>(
  () => OUTCOME_TONES[statusData.value?.last_outcome ?? ""] ?? "neutral"
);

function secretParam(key: Secret): string | undefined {
  return secretValue(edits[key]);
}

const isDirty = computed(
  () =>
    !!form.value &&
    (JSON.stringify(form.value) !== initial.value ||
      SECRETS.some((key) => secretParam(key) !== undefined))
);

const save = createResource({
  url: "helpdesk.api.github_settings.save_settings",
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
    toast.success(__("GitHub settings saved"));
  },
  onError(e: { messages?: string[] }) {
    const message = e.messages?.[0] || __("Couldn't save the GitHub settings");
    for (const [key, label] of Object.entries(LABELS))
      fieldErrors[key] = message.startsWith(`${label}:`) ? message : undefined;
    toast.error(message);
  },
});
</script>
