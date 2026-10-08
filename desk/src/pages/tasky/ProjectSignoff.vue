<template>
  <div class="flex h-full flex-col">
    <ProjectNav :project-id="projectId">
      <template #actions>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="detail.loading && !!detail.data"
          @click="detail.reload()"
        >
          <template #icon><LucideRefreshCw class="size-4" /></template>
        </Button>
      </template>
    </ProjectNav>

    <div class="flex-1 overflow-auto">
      <div
        class="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-5 md:px-6"
      >
        <router-link
          :to="{ name: 'TaskySignoffs', params: { projectId } }"
          class="inline-flex w-fit items-center gap-1 rounded text-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          <LucideArrowLeft class="size-4" aria-hidden="true" />
          {{ __("All sign-offs") }}
        </router-link>

        <TaskyState
          v-if="detail.error && !detail.data"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load this sign-off')"
          :message="loadErrorMessage(detail.error)"
        >
          <Button :label="__('Retry')" @click="detail.reload()" />
        </TaskyState>

        <!-- Loading -->
        <div
          v-else-if="!s"
          class="flex flex-col gap-3"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div class="h-6 w-1/3 animate-pulse rounded bg-surface-gray-2" />
          <div class="h-4 w-1/2 animate-pulse rounded bg-surface-gray-2" />
          <div
            class="mt-2 h-40 w-full animate-pulse rounded-xl bg-surface-gray-1"
          />
        </div>

        <template v-else>
          <!-- header -->
          <header class="flex flex-col gap-3 md:flex-row md:items-start">
            <div class="flex min-w-0 flex-1 flex-col gap-1.5">
              <div class="flex min-w-0 flex-wrap items-center gap-2">
                <h2 class="truncate text-xl font-semibold text-ink-gray-9">
                  {{ s.module_title }}
                </h2>
                <TaskyBadge
                  :label="__(status.label)"
                  :tone="status.tone"
                  :icon="status.icon"
                />
              </div>
              <dl class="flex flex-wrap gap-x-5 gap-y-1 text-sm">
                <div class="flex gap-1.5">
                  <dt class="text-ink-gray-5">{{ __("Signs off") }}</dt>
                  <dd class="text-ink-gray-8">
                    {{ s.signatory_name }}
                    <span class="font-mono text-xs text-ink-gray-5">{{
                      s.signatory_email
                    }}</span>
                  </dd>
                </div>
                <div v-if="s.trainer_name" class="flex gap-1.5">
                  <dt class="text-ink-gray-5">{{ __("Trainer") }}</dt>
                  <dd class="text-ink-gray-8">{{ s.trainer_name }}</dd>
                </div>
                <div v-if="s.training_date" class="flex gap-1.5">
                  <dt class="text-ink-gray-5">{{ __("Training date") }}</dt>
                  <dd class="tabular-nums text-ink-gray-8">
                    {{ dateFormat(s.training_date, "D MMM YYYY") }}
                  </dd>
                </div>
                <div v-if="s.template" class="flex gap-1.5">
                  <dt class="text-ink-gray-5">{{ __("Template") }}</dt>
                  <dd class="text-ink-gray-8">{{ s.template }}</dd>
                </div>
              </dl>
              <p class="flex items-center gap-1.5 text-p-sm text-ink-gray-6">
                <component
                  :is="linkLine.icon"
                  class="size-4 shrink-0"
                  aria-hidden="true"
                />
                {{ linkLine.text }}
              </p>
            </div>

            <div
              v-if="s.can_manage"
              class="flex shrink-0 flex-wrap items-center gap-2"
            >
              <Button
                v-if="s.can_edit"
                :label="__('Edit')"
                @click="showEdit = true"
              >
                <template #prefix
                  ><LucidePencil class="size-4" aria-hidden="true"
                /></template>
              </Button>
              <Button
                v-if="s.status === 'Draft' || s.status === 'Reopened'"
                variant="solid"
                :label="
                  s.link_sent_on ? __('Send new link') : __('Send to customer')
                "
                :loading="busy === 'send'"
                @click="s.link_sent_on ? (confirming = 'resend') : send()"
              >
                <template #prefix
                  ><LucideSend class="size-4" aria-hidden="true"
                /></template>
              </Button>
              <Button
                v-else-if="s.status !== 'Signed'"
                :label="__('Resend link')"
                @click="confirming = 'resend'"
              >
                <template #prefix
                  ><LucideSend class="size-4" aria-hidden="true"
                /></template>
              </Button>
              <a
                v-if="s.signed_pdf"
                :href="s.signed_pdf.file_url"
                target="_blank"
                rel="noopener"
                class="inline-flex h-7 items-center gap-1.5 rounded-md bg-surface-gray-2 px-2 text-base font-medium text-ink-gray-8 hover:bg-surface-gray-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              >
                <LucideDownload class="size-4" aria-hidden="true" />
                {{ __("Signed PDF") }}
              </a>
              <Dropdown v-if="menu.length" :options="menu" align="end">
                <Button
                  variant="ghost"
                  :aria-label="__('More actions for {0}', s.module_title)"
                >
                  <template #icon
                    ><LucideEllipsis class="size-4" aria-hidden="true"
                  /></template>
                </Button>
              </Dropdown>
            </div>
            <a
              v-else-if="s.signed_pdf"
              :href="s.signed_pdf.file_url"
              target="_blank"
              rel="noopener"
              class="inline-flex h-7 w-fit items-center gap-1.5 rounded-md bg-surface-gray-2 px-2 text-base font-medium text-ink-gray-8 hover:bg-surface-gray-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >
              <LucideDownload class="size-4" aria-hidden="true" />
              {{ __("Signed PDF") }}
            </a>
          </header>

          <!-- progress -->
          <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatTile
              compact
              :label="__('Done')"
              :value="
                __('{0} of {1}', String(s.counts.done), String(s.counts.total))
              "
              :meter="
                s.counts.total ? (s.counts.done / s.counts.total) * 100 : 0
              "
              :tone="s.counts.done === s.counts.total ? 'success' : 'neutral'"
            />
            <StatTile
              compact
              :label="__('Not clear')"
              :value="s.counts.not_clear"
              :icon="LucideCircleHelp"
              :icon-tone="s.counts.not_clear ? 'warning' : 'neutral'"
            />
            <StatTile
              compact
              :label="__('Escalated')"
              :value="s.counts.escalated"
              :icon="LucideTriangleAlert"
              :icon-tone="s.counts.escalated ? 'danger' : 'neutral'"
            />
            <StatTile
              compact
              :label="__('Waiting for an answer')"
              :value="s.counts.pending"
              :icon="LucideCircle"
            />
          </div>

          <!-- signature -->
          <SectionCard
            v-if="s.status === 'Signed'"
            :title="__('Signature')"
            :icon="LucideBadgeCheck"
            icon-class="text-success"
          >
            <dl
              class="grid grid-cols-1 gap-x-6 gap-y-2 px-4 py-3 text-sm sm:grid-cols-2"
            >
              <div class="flex gap-2">
                <dt class="w-28 shrink-0 text-ink-gray-5">
                  {{ __("Signed by") }}
                </dt>
                <dd class="text-ink-gray-8">{{ s.signer_name }}</dd>
              </div>
              <div class="flex gap-2">
                <dt class="w-28 shrink-0 text-ink-gray-5">
                  {{ __("Designation") }}
                </dt>
                <dd class="text-ink-gray-8">{{ s.signer_designation }}</dd>
              </div>
              <div class="flex gap-2">
                <dt class="w-28 shrink-0 text-ink-gray-5">{{ __("Email") }}</dt>
                <dd class="font-mono text-xs text-ink-gray-8">
                  {{ s.signer_email }}
                </dd>
              </div>
              <div class="flex gap-2">
                <dt class="w-28 shrink-0 text-ink-gray-5">
                  {{ __("Signed on") }}
                </dt>
                <dd class="tabular-nums text-ink-gray-8">
                  {{ dateFormat(s.signed_on, dateTooltipFormat) }}
                </dd>
              </div>
              <div class="flex gap-2">
                <dt class="w-28 shrink-0 text-ink-gray-5">
                  {{ __("IP address") }}
                </dt>
                <dd class="font-mono text-xs text-ink-gray-8">
                  {{ s.signer_ip || "—" }}
                </dd>
              </div>
              <div class="flex min-w-0 gap-2">
                <dt class="w-28 shrink-0 text-ink-gray-5">
                  {{ __("Audit reference") }}
                </dt>
                <dd class="min-w-0 break-all font-mono text-xs text-ink-gray-8">
                  {{ s.audit_ref }}
                </dd>
              </div>
            </dl>
          </SectionCard>

          <!-- questions -->
          <TaskyState
            v-if="!s.items.length"
            :icon="LucideClipboardList"
            :title="__('No questions yet')"
            :message="
              s.can_edit
                ? __(
                    'Add the questions the customer should confirm, then send it.'
                  )
                : __(
                    'The project lead or manager adds the questions before sending it.'
                  )
            "
          >
            <Button
              v-if="s.can_edit"
              :label="__('Add questions')"
              @click="showEdit = true"
            />
          </TaskyState>
          <SectionCard
            v-for="group in groups"
            :key="group.section"
            :title="group.section"
            :count="group.items.length"
          >
            <ol class="divide-y divide-outline-gray-1">
              <li
                v-for="item in group.items"
                :key="item.name"
                class="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-start sm:gap-4"
              >
                <div class="flex min-w-0 flex-1 gap-3">
                  <span
                    class="w-5 shrink-0 text-right font-mono text-xs tabular-nums text-ink-gray-5"
                    >{{ item.n }}</span
                  >
                  <div class="flex min-w-0 flex-1 flex-col gap-1">
                    <p class="text-p-base text-ink-gray-9">
                      {{ item.question }}
                    </p>
                    <p v-if="item.help_text" class="text-p-sm text-ink-gray-5">
                      {{ item.help_text }}
                    </p>
                    <blockquote
                      v-if="item.customer_comment"
                      class="mt-1 border-l-2 border-outline-gray-3 pl-3 text-p-sm text-ink-gray-7"
                    >
                      {{ item.customer_comment }}
                      <span class="block text-xs text-ink-gray-5">
                        {{ s.signatory_name
                        }}<template v-if="item.responded_on">
                          · {{ timeAgo(item.responded_on) }}</template
                        >
                      </span>
                    </blockquote>
                    <p
                      v-if="item.clarified_on"
                      class="flex items-start gap-1.5 text-p-sm text-ink-gray-6"
                    >
                      <LucideMessageCircleReply
                        class="mt-0.5 size-4 shrink-0"
                        aria-hidden="true"
                      />
                      <span>
                        {{
                          __(
                            "Clarified by {0}, {1}",
                            item.clarified_by_name || "",
                            timeAgo(item.clarified_on)
                          )
                        }}<template v-if="item.clarification_note"
                          >: {{ item.clarification_note }}</template
                        >
                      </span>
                    </p>
                  </div>
                </div>
                <div
                  class="flex shrink-0 flex-wrap items-center gap-2 pl-8 sm:pl-0"
                >
                  <TaskyBadge
                    :label="__(responseMeta(item.response).label)"
                    :tone="responseMeta(item.response).tone"
                    :icon="responseMeta(item.response).icon"
                  />
                  <Button
                    v-if="item.clarification_task"
                    variant="ghost"
                    :label="__('Task')"
                    :aria-label="
                      __(
                        'Open the clarification task for question {0}',
                        String(item.n)
                      )
                    "
                    @click="
                      openTask = {
                        name: item.clarification_task,
                        project: s.project,
                        project_name: s.project_name,
                      }
                    "
                  >
                    <template #prefix
                      ><LucideSquareCheck class="size-4" aria-hidden="true"
                    /></template>
                  </Button>
                  <Button
                    v-if="s.can_manage && needsFollowUp(item.response)"
                    :label="__('Mark clarified')"
                    :aria-label="
                      __('Mark question {0} clarified', String(item.n))
                    "
                    @click="startClarify(item)"
                  />
                </div>
              </li>
            </ol>
          </SectionCard>

          <!-- history -->
          <SectionCard
            :title="__('History')"
            :description="
              __(
                'Every step, with who took it and when. The customer\'s steps include their IP address in the record.'
              )
            "
          >
            <ol class="divide-y divide-outline-gray-1">
              <li
                v-for="(entry, i) in visibleLog"
                :key="i"
                class="flex flex-col gap-0.5 px-4 py-2.5 text-sm sm:flex-row sm:items-baseline sm:gap-4"
              >
                <span class="w-40 shrink-0 tabular-nums text-ink-gray-5">
                  <time
                    :datetime="entry.at"
                    :title="dateFormat(entry.at, dateTooltipFormat)"
                    >{{ dateFormat(entry.at, "D MMM, h:mm A") }}</time
                  >
                </span>
                <span class="min-w-0 flex-1 text-ink-gray-8">
                  <span class="font-medium">{{ entry.event }}</span>
                  <template v-if="entry.item && itemNumber[entry.item]">
                    ·
                    {{
                      __("question {0}", String(itemNumber[entry.item]))
                    }}</template
                  >
                  <template v-if="entry.detail"
                    >:
                    <span class="text-ink-gray-7">{{
                      entry.detail
                    }}</span></template
                  >
                </span>
                <span class="shrink-0 text-ink-gray-6">{{
                  entry.by_name
                }}</span>
              </li>
            </ol>
            <div
              v-if="s.log.length > visibleLog.length"
              class="border-t border-outline-gray-1 px-4 py-2"
            >
              <Button
                variant="ghost"
                :label="__('Show all {0}', String(s.log.length))"
                @click="showAllLog = true"
              />
            </div>
          </SectionCard>
        </template>
      </div>
    </div>

    <SignoffFormDialog
      v-if="s?.can_edit"
      v-model:open="showEdit"
      :project-id="projectId"
      :signoff="s"
      @saved="detail.reload()"
    />

    <TaskDetailDialog
      v-model:task="openTask"
      :mine="s?.trainer === auth.userId"
      @changed="detail.reload()"
    />

    <!-- mark clarified -->
    <Dialog
      :open="!!clarifying"
      :title="__('Mark clarified')"
      size="lg"
      @update:open="(v: boolean) => !v && (clarifying = null)"
    >
      <div class="flex flex-col gap-3">
        <p class="text-p-sm text-ink-gray-7">{{ clarifying?.question }}</p>
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "The item goes back to the customer to answer again, its task is closed, and the customer gets an email with a new link."
            )
          }}
        </p>
        <FormControl
          v-model="clarifyNote"
          type="textarea"
          :label="__('Note to the customer (optional)')"
          :placeholder="__('e.g. We went through it on a call on 12 Oct.')"
          :rows="3"
          maxlength="1000"
        />
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="clarifying = null" />
          <Button
            variant="solid"
            :label="__('Mark clarified')"
            :loading="busy === 'clarify'"
            @click="clarify"
          />
        </div>
      </template>
    </Dialog>

    <!-- reopen -->
    <Dialog
      :open="confirming === 'reopen'"
      :title="__('Reopen sign-off?')"
      size="lg"
      @update:open="(v: boolean) => !v && (confirming = null)"
    >
      <div class="flex flex-col gap-3">
        <p class="text-p-sm text-ink-gray-7">
          {{
            __(
              "The customer's signature is withdrawn and recorded in the history. The signed PDF stays on the project. You can then change the questions and send a new link."
            )
          }}
        </p>
        <FormControl
          v-model="reopenReason"
          type="textarea"
          :label="__('Reason')"
          :placeholder="__('e.g. The customer asked to add the GST report.')"
          :rows="3"
          maxlength="1000"
          required
        />
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="confirming = null" />
          <Button
            variant="solid"
            theme="red"
            :label="__('Reopen sign-off')"
            :loading="busy === 'reopen'"
            :disabled="!reopenReason.trim()"
            @click="
              run(
                'reopen',
                'reopen_signoff',
                { reason: reopenReason },
                __('Sign-off reopened')
              )
            "
          />
        </div>
      </template>
    </Dialog>

    <!-- resend, revoke, delete -->
    <Dialog
      :open="
        confirming === 'resend' ||
        confirming === 'revoke' ||
        confirming === 'delete'
      "
      :title="confirmCopy.title"
      :message="confirmCopy.message"
      size="md"
      @update:open="(v: boolean) => !v && (confirming = null)"
    >
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="confirming = null" />
          <Button
            variant="solid"
            :theme="confirming === 'resend' ? 'gray' : 'red'"
            :label="confirmCopy.action"
            :loading="!!busy"
            @click="confirmCopy.run()"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { dateFormat, dateTooltipFormat, errorText, timeAgo } from "@/utils";
import {
  Button,
  Dialog,
  Dropdown,
  FormControl,
  call,
  createResource,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import LucideArrowLeft from "~icons/lucide/arrow-left";
import LucideBadgeCheck from "~icons/lucide/badge-check";
import LucideCircle from "~icons/lucide/circle";
import LucideClipboardList from "~icons/lucide/clipboard-list";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleHelp from "~icons/lucide/circle-help";
import LucideDownload from "~icons/lucide/download";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideLink from "~icons/lucide/link";
import LucideLinkOff from "~icons/lucide/link-2-off";
import LucideMessageCircleReply from "~icons/lucide/message-circle-reply";
import LucidePencil from "~icons/lucide/pencil";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideRotateCcw from "~icons/lucide/rotate-ccw";
import LucideSend from "~icons/lucide/send";
import LucideSquareCheck from "~icons/lucide/square-check";
import LucideTrash2 from "~icons/lucide/trash-2";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import ProjectNav from "./components/ProjectNav.vue";
import SignoffFormDialog from "./components/SignoffFormDialog.vue";
import TaskDetailDialog, {
  type TaskRef,
} from "./components/TaskDetailDialog.vue";
import {
  groupBySection,
  needsFollowUp,
  responseMeta,
  signoffStatusMeta,
  type SignoffQuestion,
} from "./signoffMeta";
import { loadErrorMessage } from "./taskMeta";

interface SignoffItem extends SignoffQuestion {
  name: string;
  response: string;
  customer_comment?: string | null;
  responded_on?: string | null;
  clarification_task?: string | null;
  clarified_on?: string | null;
  clarified_by_name?: string | null;
  clarification_note?: string | null;
}

interface SignoffDetail {
  name: string;
  project: string;
  project_name: string;
  module_title: string;
  template?: string | null;
  status: string;
  training_date?: string | null;
  trainer?: string | null;
  trainer_name?: string | null;
  signatory_contact?: string | null;
  signatory_name: string;
  signatory_email: string;
  link_open: boolean;
  link_sent_on?: string | null;
  link_expires_on?: string | null;
  signed_on?: string | null;
  signer_name?: string | null;
  signer_designation?: string | null;
  signer_email?: string | null;
  signer_ip?: string | null;
  audit_ref?: string | null;
  signed_pdf?: { file_name: string; file_url: string } | null;
  counts: {
    total: number;
    done: number;
    not_clear: number;
    escalated: number;
    pending: number;
  };
  items: SignoffItem[];
  log: {
    event: string;
    item?: string | null;
    detail?: string | null;
    by_name?: string | null;
    at: string;
  }[];
  can_manage: boolean;
  can_edit: boolean;
}

const props = defineProps<{ projectId: string; signoffId: string }>();
const router = useRouter();
const auth = useAuthStore();

const detail = createResource({
  url: "helpdesk.api.project_signoff.get_signoff",
  makeParams: () => ({ signoff: props.signoffId }),
  auto: true,
  onError() {},
});
watch(
  () => props.signoffId,
  () => detail.reload()
);

const s = computed(() => detail.data as SignoffDetail | undefined);
const status = computed(() => signoffStatusMeta(s.value?.status ?? "Draft"));
const groups = computed(() =>
  groupBySection(s.value?.items ?? [], __("General"))
);
const itemNumber = computed(() =>
  Object.fromEntries(
    (s.value?.items ?? []).map((item, i) => [item.name, i + 1])
  )
);

const showAllLog = ref(false);
const visibleLog = computed(() =>
  showAllLog.value ? s.value?.log ?? [] : (s.value?.log ?? []).slice(0, 8)
);

const linkLine = computed(() => {
  const d = s.value!;
  if (d.status === "Signed")
    return {
      icon: LucideBadgeCheck,
      text: __("Signed {0}", dateFormat(d.signed_on, "D MMM YYYY, h:mm A")),
    };
  if (d.link_open)
    return {
      icon: LucideLink,
      text: __(
        "Link sent {0}; works until {1}",
        dateFormat(d.link_sent_on, "D MMM YYYY"),
        dateFormat(d.link_expires_on, "D MMM YYYY")
      ),
    };
  if (d.link_sent_on && d.status !== "Draft")
    return {
      icon: LucideLinkOff,
      text: __(
        "No working link: it was revoked or has expired. Resend it to continue."
      ),
    };
  return { icon: LucideLinkOff, text: __("Not sent to the customer yet") };
});

const showEdit = ref(false);
const openTask = ref<TaskRef | null>(null);
const busy = ref<string | null>(null);
const confirming = ref<"resend" | "revoke" | "delete" | "reopen" | null>(null);
const reopenReason = ref("");
const clarifying = ref<SignoffItem | null>(null);
const clarifyNote = ref("");

const menu = computed(() => {
  const d = s.value;
  if (!d?.can_manage) return [];
  const items = [];
  if (d.link_open)
    items.push({
      label: __("Revoke link"),
      icon: LucideLinkOff,
      onClick: () => (confirming.value = "revoke"),
    });
  if (d.status === "Signed")
    items.push({
      label: __("Reopen sign-off"),
      icon: LucideRotateCcw,
      onClick: () => {
        reopenReason.value = "";
        confirming.value = "reopen";
      },
    });
  if (d.status === "Draft")
    items.push({
      label: __("Delete draft"),
      icon: LucideTrash2,
      onClick: () => (confirming.value = "delete"),
    });
  return items;
});

const confirmCopy = computed(() => {
  const email = s.value?.signatory_email ?? "";
  if (confirming.value === "revoke")
    return {
      title: __("Revoke the link?"),
      message: __(
        "The link stops working at once, and the customer can't answer or sign until you send a new one."
      ),
      action: __("Revoke link"),
      run: () => run("revoke", "revoke_signoff_link", {}, __("Link revoked")),
    };
  if (confirming.value === "delete")
    return {
      title: __("Delete this draft?"),
      message: __("The customer has never seen it. This can't be undone."),
      action: __("Delete draft"),
      run: () => remove(),
    };
  return {
    title: __("Send a new link?"),
    message: __(
      "{0} gets a new link and the earlier one stops working.",
      email
    ),
    action: __("Send new link"),
    run: () => send(),
  };
});

async function run(
  key: string,
  method: string,
  args: Record<string, unknown>,
  success: string
) {
  busy.value = key;
  try {
    await call(`helpdesk.api.project_signoff.${method}`, {
      signoff: props.signoffId,
      ...args,
    });
    toast.success(success);
    confirming.value = null;
    clarifying.value = null;
    await detail.reload();
  } catch (e) {
    toast.error(errorText(e, __("That didn't work. Try again.")));
  } finally {
    busy.value = null;
  }
}

function send() {
  run(
    "send",
    "send_signoff_link",
    {},
    __("Link sent to {0}", s.value?.signatory_email ?? "")
  );
}

function startClarify(item: SignoffItem) {
  clarifyNote.value = "";
  clarifying.value = item;
}

function clarify() {
  if (!clarifying.value) return;
  run(
    "clarify",
    "mark_item_clarified",
    { item: clarifying.value.name, note: clarifyNote.value },
    __("Marked clarified; the customer has been emailed")
  );
}

async function remove() {
  busy.value = "delete";
  try {
    await call("helpdesk.api.project_signoff.delete_signoff", {
      signoff: props.signoffId,
    });
    toast.success(__("Draft deleted"));
    router.replace({
      name: "TaskySignoffs",
      params: { projectId: props.projectId },
    });
  } catch (e) {
    toast.error(errorText(e, __("Couldn't delete the draft.")));
  } finally {
    busy.value = null;
    confirming.value = null;
  }
}
</script>
