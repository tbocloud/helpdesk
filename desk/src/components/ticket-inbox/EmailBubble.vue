<template>
  <!-- one email in the ticket's conversation (Phase 16): the customer's on the left (white), ours on
       the right (blue, "Sent to Aisha"); the body in the same safe frame as before -->
  <article
    :id="activity.key"
    class="flex w-full max-w-2xl gap-2.5"
    :class="ours ? 'ms-auto flex-row-reverse' : ''"
    :aria-label="label"
  >
    <Avatar
      v-if="!ours || !byCopilot"
      size="lg"
      class="mt-6 shrink-0"
      :label="activity.sender?.full_name || activity.sender?.name"
      :image="getUser(activity.sender?.name).user_image"
    />
    <span
      v-else
      class="mt-6 flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-gray-3 text-ink-gray-7"
      aria-hidden="true"
    >
      <LucideSparkles class="size-4" />
    </span>
    <div class="min-w-0 flex-1" :class="ours && 'flex flex-col items-end'">
      <p
        class="mb-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-sm"
        :class="ours && 'justify-end'"
      >
        <span
          v-if="ours"
          class="inline-flex items-center gap-1 font-medium text-ink-blue-6"
        >
          <LucideMail class="size-3.5" aria-hidden="true" />
          {{
            byCopilot
              ? __("Automatic update to {0}", contactFirst)
              : __("Sent to {0}", contactFirst)
          }}
        </span>
        <span v-if="ours" class="text-ink-gray-4" aria-hidden="true">·</span>
        <span class="font-medium text-ink-gray-9">{{ author }}</span>
        <Tooltip :text="dateFormat(activity.creation, dateTooltipFormat)">
          <time class="text-ink-gray-5">{{ clock(activity.creation) }}</time>
        </Tooltip>
        <span v-if="!ours && activity.isFirstEmail" class="text-ink-gray-5"
          >· {{ __("via Email") }}</span
        >
        <span
          v-if="activity.aiDrafted"
          class="inline-flex h-5 items-center gap-1 rounded-md px-1.5 text-xs font-medium text-ink-gray-6 ring-1 ring-inset ring-outline-gray-3"
          :title="__('Sent by this agent from a draft written by TBO AI')"
        >
          <LucideSparkles class="size-3.5" aria-hidden="true" />
          {{ __("AI-drafted") }}
        </span>
        <Badge
          v-if="problem"
          :label="__(problem.label)"
          variant="subtle"
          :theme="problem.color"
        />
      </p>
      <div
        class="group relative w-full rounded-2xl px-3.5 py-2.5"
        :class="
          ours
            ? 'rounded-se-md border border-outline-blue-1 bg-surface-blue-1'
            : 'rounded-ss-md border border-outline-gray-2 bg-surface-base shadow-[0_1px_2px_rgb(16_18_24/0.05)]'
        "
      >
        <p
          v-if="recipients"
          class="mb-1.5 truncate text-xs text-ink-gray-5"
          :title="recipients"
        >
          {{ recipients }}
        </p>
        <EmailContent :content="activity.content" />
        <div
          v-if="activity.attachments?.length"
          class="mt-2 flex flex-wrap gap-2"
        >
          <AttachmentItem
            v-for="a in activity.attachments"
            :key="a.file_url"
            :label="a.file_name"
            :url="a.file_url"
          />
        </div>
      </div>
      <div
        v-if="!ours"
        class="mt-1 flex items-center gap-0.5"
        :aria-label="__('Answer this email')"
        role="group"
      >
        <Button
          variant="ghost"
          size="sm"
          :label="__('Reply')"
          @click="emit('reply', replyTo(email, user))"
        >
          <template #prefix><ReplyIcon class="size-4" /></template>
        </Button>
        <Button
          variant="ghost"
          size="sm"
          :label="__('Reply all')"
          @click="emit('reply', replyAllTo(email, user))"
        >
          <template #prefix><ReplyAllIcon class="size-4" /></template>
        </Button>
        <Dropdown
          v-if="canSplit"
          placement="left"
          :options="[
            {
              label: __('Split into a new ticket'),
              icon: LucideSplit,
              onClick: () => (showSplit = true),
            },
          ]"
        >
          <Button variant="ghost" size="sm" :label="__('More')">
            <template #icon>
              <LucideEllipsis class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </Dropdown>
      </div>
    </div>
    <TicketSplitModal
      v-if="canSplit"
      v-model="showSplit"
      :ticket_id="activity.name"
      :communication_id="activity.name"
    />
  </article>
</template>

<script setup lang="ts">
import AttachmentItem from "@/components/AttachmentItem.vue";
import EmailContent from "@/components/EmailContent.vue";
import { replyAllTo, replyTo, type ReplyTarget } from "@/components/emailReply";
import { ReplyAllIcon, ReplyIcon } from "@/components/icons";
import TicketSplitModal from "@/components/ticket/TicketSplitModal.vue";
import { useAuthStore } from "@/stores/auth";
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { dateFormat, dateTooltipFormat } from "@/utils";
import {
  Avatar,
  Badge,
  Button,
  dayjsLocal,
  Dropdown,
  Tooltip,
} from "frappe-ui";
import { computed, ref } from "vue";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideMail from "~icons/lucide/mail";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideSplit from "~icons/lucide/split";

const props = defineProps<{
  activity: any;
  contactFirst: string;
  ticketStatus: string;
}>();
const emit = defineEmits<{ reply: [target: ReplyTarget] }>();

const { getUser } = useUserStore();
const auth = useAuthStore();
const user = computed(() => String(auth.userId || ""));
const showSplit = ref(false);

const ours = computed(() => props.activity.direction === "Sent");
const byCopilot = computed(() => ours.value && props.activity.byAutomation);
const author = computed(() =>
  byCopilot.value
    ? __("TBO Copilot")
    : props.activity.sender?.full_name ||
      props.activity.sender?.name ||
      __("Someone")
);
const email = computed(() => ({
  content: props.activity.content,
  sender: props.activity.sender,
  to: props.activity.to,
  cc: props.activity.cc,
  bcc: props.activity.bcc,
}));
// a later email of the customer's can become its own ticket (not the one that opened it)
const canSplit = computed(
  () => !props.activity.isFirstEmail && props.ticketStatus !== "Closed"
);
// To and Cc only when there is more than the customer to tell
const recipients = computed(() => {
  const cc = String(props.activity.cc || "").trim();
  if (!cc) return "";
  return __("Cc: {0}", cc);
});
// a send that didn't go through, or hasn't yet
const problem = computed(() => {
  const s = props.activity.deliveryStatus;
  if (!ours.value || !s || ["Sent", "Clicked", "Opened", "Read"].includes(s))
    return null;
  return { label: s, color: s === "Error" ? "red" : "orange" };
});
const label = computed(() =>
  ours.value
    ? __("Email from {0} to the customer", author.value)
    : __("Email from {0}", author.value)
);

function clock(at: string) {
  return dayjsLocal(at).format("h:mm A");
}
</script>
