<template>
  <!-- the support team's messages sit on the panel surface; the customer's own on gray -->
  <article
    class="rounded-lg border px-4 pb-3 pt-3 text-base leading-6"
    :class="
      fromSupport
        ? 'border-outline-gray-2 bg-surface-base'
        : 'border-transparent bg-surface-gray-1'
    "
  >
    <header class="mb-2 flex min-w-0 items-center gap-2">
      <Avatar size="sm" :label="user?.name" :image="user?.image" />
      <span class="min-w-0 truncate text-sm font-medium text-ink-gray-8">
        {{ isYou ? __("You") : user?.name }}
      </span>
      <TaskyBadge v-if="fromSupport" :label="brandName" />
      <Tooltip :text="dateFormat(date, dateTooltipFormat)">
        <time
          :datetime="date"
          class="ml-auto shrink-0 text-sm tabular-nums text-ink-gray-5"
        >
          {{ timeAgo(date) }}
        </time>
      </Tooltip>
    </header>

    <EmailContent :content="sanitize(content)" />
    <ul
      v-if="attachments.length"
      class="mt-2 flex flex-wrap gap-2"
      :aria-label="__('Attachments')"
    >
      <li v-for="a in attachments" :key="a.file_url">
        <AttachmentItem :label="a.file_name" :url="a.file_url" />
      </li>
    </ul>
  </article>
</template>

<script setup lang="ts">
import { AttachmentItem } from "@/components";
import EmailContent from "@/components/EmailContent.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import { useConfigStore } from "@/stores/config";
import { __ } from "@/translation";
import { UserInfo } from "@/types";
import { dateFormat, dateTooltipFormat, timeAgo } from "@/utils";
import { Avatar, Tooltip } from "frappe-ui";
import { storeToRefs } from "pinia";
import sanitizeHtml from "sanitize-html";

interface Attachment {
  file_name: string;
  file_url: string;
}

interface P {
  content: string;
  date: string;
  user: UserInfo;
  /** sent by the support team (an agent's reply) rather than the customer */
  fromSupport?: boolean;
  /** sent by the person viewing the ticket */
  isYou?: boolean;
  attachments?: Attachment[];
}

withDefaults(defineProps<P>(), {
  fromSupport: false,
  isYou: false,
  attachments: () => [],
});

const { brandName } = storeToRefs(useConfigStore());

// emails carry images and video, so this keeps them (sanitizeRichText would drop them)
function sanitize(html: string) {
  return sanitizeHtml(html, {
    allowedTags: sanitizeHtml.defaults.allowedTags.concat(["img", "video"]),
    allowedAttributes: {
      a: ["href"],
      video: ["src", "controls"],
      img: ["src", "width", "height"],
      table: ["border", "cellpadding", "cellspacing", "width", "data-type"],
      td: ["colspan", "rowspan", "width", "align", "valign"],
      th: ["colspan", "rowspan", "width", "align", "valign"],
    },
  });
}
</script>
