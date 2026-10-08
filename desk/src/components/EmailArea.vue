<template>
  <div
    :id="`communication-${name}`"
    v-bind="$attrs"
    class="grow cursor-pointer overflow-hidden rounded-xl border border-outline-gray-2 text-base leading-6 shadow-[0_1px_2px_rgb(16_18_24/0.04),0_1px_3px_rgb(16_18_24/0.06)] transition-colors"
    :class="direction === 'Sent' ? 'bg-surface-gray-1' : 'bg-surface-base'"
  >
    <div
      class="flex items-center justify-between gap-2"
      :class="isMobileView && 'items-start'"
    >
      <!-- email design for mobile -->
      <div v-if="isMobileView" class="flex items-center gap-2 text-sm">
        <div class="leading-tight">
          <p>{{ sender.full_name || "Guest" }}</p>
          <p class="flex items-center gap-1 text-xs text-ink-gray-6">
            <component :is="origin.icon" class="size-3.5" aria-hidden="true" />
            {{ origin.label }}
          </p>
          <Tooltip :text="dateFormat(creation, dateTooltipFormat)">
            <p class="text-xs md:text-sm text-ink-gray-5">
              {{ timeAgo(creation) }}
            </p>
          </Tooltip>
          <p class="sm:flex hidden text-sm text-ink-gray-5" v-if="sender.name">
            {{ "<" + sender.name + ">" }}
          </p>
        </div>
      </div>
      <!-- email design for desktop -->
      <div v-else class="flex min-w-0 items-center gap-2">
        <span class="text-sm font-semibold text-ink-gray-9">{{
          sender.full_name || "Guest"
        }}</span>
        <span
          v-if="sender.name"
          class="hidden truncate font-mono text-xs text-ink-gray-5 sm:inline"
          >{{ sender.name }}</span
        >
        <span
          class="inline-flex h-5 items-center gap-1 rounded-md px-1.5 text-xs font-medium text-ink-gray-6 ring-1 ring-inset ring-outline-gray-3"
        >
          <component :is="origin.icon" class="size-3.5" aria-hidden="true" />
          {{ origin.label }}
        </span>
        <span
          v-if="aiDrafted"
          class="inline-flex h-5 items-center gap-1 rounded-md px-1.5 text-xs font-medium text-ink-gray-6 ring-1 ring-inset ring-outline-gray-3"
          :title="__('Sent by this agent from a draft written by TBO AI')"
        >
          <LucideSparkles class="size-3.5" aria-hidden="true" />
          {{ __("AI-drafted") }}
        </span>
      </div>

      <div class="flex gap-2 items-center">
        <div class="gap-0.5 flex items-center">
          <Badge
            v-if="status.label && !ticket?.doc?.via_customer_portal"
            :label="__(status.label)"
            variant="subtle"
            :theme="status.color"
            class="mr-1.5"
          />
          <Tooltip
            :text="dateFormat(creation, dateTooltipFormat)"
            v-if="!isMobileView"
          >
            <p class="text-xs md:text-sm text-ink-gray-5">
              {{ timeAgo(creation) }}
            </p>
          </Tooltip>
        </div>
        <div class="flex items-center gap-1">
          <Button :tooltip="__('Reply')" variant="ghost" @click="reply">
            <template #icon>
              <ReplyIcon class="text-ink-gray-7" />
            </template>
          </Button>
          <Button :tooltip="__('Reply All')" variant="ghost" @click="replyAll">
            <template #icon>
              <ReplyAllIcon class="text-ink-gray-7" />
            </template>
          </Button>
          <Dropdown
            v-if="showSplitOption"
            :placement="'right'"
            :options="[
              {
                label: 'Split Ticket',
                icon: LucideSplit,
                onClick: () => (showSplitModal = true),
              },
            ]"
          >
            <Button
              icon="lucide-more-horizontal"
              class="!text-ink-gray-7"
              variant="ghost"
            />
          </Dropdown>
        </div>
      </div>
    </div>
    <div class="text-p-sm text-ink-gray-5">
      <template
        v-for="(val, label) in { To: to, cc: cc, bcc: bcc }"
        :key="label"
      >
        <span v-if="val" class="mr-1.5">
          <span class="mr-1 text-ink-gray-7">{{ label }}:</span>
          <span> {{ normalizeAndFilter(val).join(", ") }}</span>
        </span>
      </template>
    </div>
    <div class="border-0 border-t my-3 border-outline-gray-2 !-mx-4" />
    <EmailContent :content="content" />
    <div class="flex flex-wrap gap-2">
      <AttachmentItem
        v-for="a in attachments"
        :key="a.file_url"
        :label="a.file_name"
        :url="a.file_url"
      />
    </div>
  </div>
  <TicketSplitModal
    v-model="showSplitModal"
    :ticket_id="name"
    :communication_id="name"
  />
</template>

<script setup lang="ts">
import { AttachmentItem } from "@/components";
import { useScreenSize } from "@/composables/screen";
import { useAuthStore } from "@/stores/auth";
import { TicketSymbol } from "@/types";
import { dateFormat, dateTooltipFormat, timeAgo } from "@/utils";
import { Dropdown } from "frappe-ui";
import { storeToRefs } from "pinia";
import { computed, inject, ref } from "vue";
import { __ } from "@/translation";
import LucideMail from "~icons/lucide/mail";
import LucideSend from "~icons/lucide/send";
import LucideUserRound from "~icons/lucide/user-round";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideSplit from "~icons/lucide/split";
import { ReplyAllIcon, ReplyIcon } from "./icons";
import TicketSplitModal from "./ticket/TicketSplitModal.vue";

const props = defineProps({
  activity: {
    type: Object,
    required: true,
  },
  showSplitOption: {
    type: Boolean,
    default: false,
  },
});

const {
  sender,
  to,
  cc,
  bcc,
  creation,
  subject,
  attachments,
  content,
  name,
  deliveryStatus,
  aiDrafted,
  direction,
} = props.activity;

// who wrote it, in words: colour alone wouldn't tell the two apart
const origin =
  direction === "Sent"
    ? { label: __("Agent reply"), icon: LucideSend }
    : direction === "Received"
    ? { label: __("Customer"), icon: LucideUserRound }
    : { label: __("Email"), icon: LucideMail };

const emit = defineEmits(["reply"]);
const ticket = inject(TicketSymbol)!;

const auth = storeToRefs(useAuthStore());

const { isMobileView } = useScreenSize();

const showSplitModal = ref(false);

const status = computed(() => {
  let _status = deliveryStatus;
  let indicator_color = "red";
  if (["Sent", "Clicked"].includes(_status)) {
    indicator_color = "green";
  } else if (["Sending", "Scheduled"].includes(_status)) {
    indicator_color = "orange";
  } else if (["Opened", "Read"].includes(_status)) {
    indicator_color = "blue";
  } else if (_status == "Error") {
    indicator_color = "red";
  }
  return { label: _status, color: indicator_color };
});

const normalizeAndFilter = (
  field: string | string[],
  valuesToExclude: string[] = []
) => {
  let arr = [];
  let current = "";
  let inQuotes = false;
  if (typeof field === "string") {
    for (let char of field) {
      if (char === '"') {
        inQuotes = !inQuotes;
        current += char;
      } else if (char === "," && !inQuotes) {
        arr.push(current.trim());
        current = "";
      } else {
        current += char;
      }
    }
    if (current) arr.push(current.trim());
  } else {
    arr = field || [];
  }
  return arr.filter(Boolean).filter((item) => !valuesToExclude.includes(item));
};

const reply = () => {
  const user = auth.user.value;
  emit("reply", {
    content: content,
    to: user === sender.name ? to : sender.name,
  });
};

const replyAll = () => {
  const user = auth.user.value;
  const exclude = [user, sender.name];
  const filteredTo = normalizeAndFilter(to, exclude);
  const filteredCc = normalizeAndFilter(cc, exclude);
  const filteredBcc = normalizeAndFilter(bcc, exclude);

  let _to, _cc, _bcc;

  if (user === sender.name) {
    // User is the sender, reply to all original recipients
    _to = filteredTo.join(", ");
    _cc = filteredCc;
    _bcc = filteredBcc;
  } else {
    // User is a recipient, reply to sender with all other recipients in cc
    _to = sender.name;
    _cc = [...filteredTo, ...filteredCc];
    _bcc = filteredBcc;
  }

  emit("reply", {
    content: content,
    to: _to,
    cc: _cc.filter(Boolean),
    bcc: _bcc.filter(Boolean),
  });
};
</script>

<style>
.email-content {
  max-width: 100%;
}
.email-content > * {
  display: flex;
  flex-direction: column;
  flex-wrap: nowrap;
}
</style>
