<template>
  <ActivityHeader :title="title" />
  <FadedScrollableDiv
    class="flex flex-col flex-1 overflow-y-auto"
    :mask-length="20"
  >
    <div v-if="activities.length" class="activities flex-1 h-full mt-0.5">
      <div
        v-for="(activity, i) in activities"
        :key="activity.key"
        class="activity mt-2"
        tabindex="0"
        :id="activity.key"
      >
        <!-- single activity -->
        <div
          class="w-full px-6 md:px-5 grid grid-cols-[30px_minmax(auto,_1fr)] gap-2 sm:gap-4"
        >
          <div
            class="relative flex justify-center after:absolute after:left-[50%] after:top-3 after:-z-10 after:border-l after:border-outline-elevation-2"
            :class="[
              i != activities.length - 1 && 'after:h-full',
              !['email', 'feedback', 'call', 'comment'].includes(
                activity.type
              ) && 'after:top-6',
            ]"
          >
            <div
              class="z-1 flex items-center justify-center rounded-full bg-surface-base"
              :class="[
                ['email', 'feedback'].includes(activity.type)
                  ? 'my-1 h-9 w-9'
                  : 'h-6 w-6',
                !['email', 'feedback', 'call', 'comment'].includes(
                  activity.type
                ) && 'mt-[2px]',
              ]"
            >
              <Avatar
                v-if="activity.type === 'email' || activity.type === 'feedback'"
                size="lg"
                :label="activity.sender?.full_name"
                :image="getUser(activity.sender?.name).user_image"
                class="bg-surface-base absolute left-[0.7px]"
              />
              <Avatar
                v-else-if="activity.type === 'comment'"
                size="md"
                :label="activity.commenter"
                :image="getUser(activity.commentedBy).user_image"
                class="absolute left-[3px] top-1"
              />
              <FeatherIcon
                v-else-if="activity.type === 'call'"
                :name="
                  activity.call_type === 'Incoming'
                    ? 'phone-incoming'
                    : 'phone-outgoing'
                "
                class="text-ink-gray-5 left-[7.5px] size-4"
              />
              <DotIcon
                v-else
                class="text-ink-gray-5 absolute left-[7.5px] top-[6px]"
              />
            </div>
          </div>
          <div
            class="mb-4 flex flex-1"
            :class="[
              i == activities.length - 1 && 'mb-5',
              !['email', 'feedback', 'call', 'comment'].includes(
                activity.type
              ) && 'mt-[2px]',
            ]"
          >
            <!-- Activity (Phase 15): one line per event; the message itself is on the Customer tab -->
            <button
              v-if="
                compact &&
                (['email', 'call'].includes(activity.type) ||
                  (activity.type === 'comment' && !activity.byAutomation))
              "
              type="button"
              class="-mx-1 flex w-full min-w-0 items-center justify-between gap-3 rounded px-1 text-start text-base hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              :title="__('Open it on the Customer tab')"
              @click="emit('open', activity)"
            >
              <span class="min-w-0 truncate text-ink-gray-5">
                <span class="font-medium text-ink-gray-8">{{
                  oneLine(activity).who
                }}</span>
                {{ oneLine(activity).what }}
              </span>
              <Tooltip :text="dateFormat(activity.creation, dateTooltipFormat)">
                <span class="shrink-0 text-sm text-ink-gray-5">{{
                  timeAgo(activity.creation)
                }}</span>
              </Tooltip>
            </button>
            <EmailArea
              v-else-if="activity.type === 'email'"
              :activity="activity"
              :show-split-option="
                !activity.isFirstEmail && ticketStatus !== 'Closed'
              "
              class="px-4 py-2"
              @reply="(e) => emit('email:reply', e)"
            />
            <CommentBox
              v-else-if="activity.type === 'comment'"
              :activity="activity"
              @update="() => emit('update')"
            />
            <CallArea
              v-else-if="activity.type === 'call'"
              :activity="activity"
            />
            <FeedbackBox
              :activity="activity"
              v-else-if="activity.type === 'feedback'"
            />
            <HistoryBox v-else :activity="activity" />
          </div>
        </div>
      </div>
    </div>
    <div
      v-else
      class="h-screen flex flex-col items-center justify-center gap-3 text-2xl-medium text-ink-gray-4"
    >
      <component :is="emptyTextIcon" class="h-7.5 w-7.5" />
      <span class="text-lg-medium text-ink-gray-8">{{ __(emptyText) }}</span>
    </div>
  </FadedScrollableDiv>
</template>

<script setup lang="ts">
import { FadedScrollableDiv } from "@/components";
import {
  ActivityIcon,
  CommentIcon,
  DotIcon,
  EmailIcon,
  PhoneIcon,
} from "@/components/icons";
import { useUserStore } from "@/stores/user";
import { TicketActivity } from "@/types";
import { isElementInViewport } from "@/utils";
import { __ } from "@/translation";
import { dateFormat, dateTooltipFormat, timeAgo } from "@/utils";
import { Avatar, FeatherIcon, Tooltip } from "frappe-ui";
import { PropType, computed, h, inject, nextTick, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import FeedbackBox from "../ticket-agent/FeedbackBox.vue";
import CommentBox from "@/components/CommentBox.vue";
import EmailArea from "@/components/EmailArea.vue";
import HistoryBox from "@/components/HistoryBox.vue";

const props = defineProps({
  activities: {
    type: Array as PropType<TicketActivity[]>,
    required: true,
  },
  title: {
    type: String,
    required: true,
  },
  ticketStatus: {
    type: String,
    default: "",
  },
  /** one line per email, note and call (the Activity tab) */
  compact: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["email:reply", "update", "open"]);

function oneLine(activity: any): { who: string; what: string } {
  if (activity.type === "email")
    return {
      who: activity.sender?.full_name || activity.sender?.name || "",
      what:
        activity.direction === "Sent"
          ? __("replied to the customer")
          : __("wrote by email"),
    };
  if (activity.type === "comment")
    return {
      who: activity.commenter || "",
      what: __("added an internal note"),
    };
  return {
    who: activity.caller || __("Someone"),
    what: __("made a call ({0})", [activity.duration || "0s"]),
  };
}

const route = useRoute();
const router = useRouter();

const { getUser } = useUserStore();
const makeCall = inject<() => void>("makeCall");

const emptyText = computed(() => {
  if (props.title === "Emails") return "No email communications";
  if (props.title === "Comments") return "No comments found";
  if (props.title === "Calls") return "No calls made";

  return "No activity found";
});

const emptyTextIcon = computed(() => {
  let icon = ActivityIcon;
  if (props.title == "Emails") {
    icon = EmailIcon;
  } else if (props.title == "Comments") {
    icon = CommentIcon;
  } else if (props.title == "Calls") {
    icon = PhoneIcon;
  }
  return h(icon, { class: "text-ink-gray-4" });
});

onMounted(() => {
  nextTick(() => {
    document.querySelector(".activity")?.focus();
  });
});

function scrollToLatestActivity() {
  if (route.hash) {
    scrollToHash();
    return;
  }
  setTimeout(() => {
    let el;
    let e = document.getElementsByClassName("activity");
    el = e[e.length - 1];
    if (el && !isElementInViewport(el)) {
      el.scrollIntoViewIfNeeded();
      el.focus();
    }
  }, 500);
}
function scrollToHash() {
  const hash = route.hash;
  if (hash) {
    // Remove the # symbol
    const elementId = hash.substring(1);

    nextTick(() => {
      // Wait for activities to be rendered
      setTimeout(() => {
        const element = document.getElementById(elementId);
        if (element) {
          (element as any).scrollIntoViewIfNeeded();

          // Add highlight effect using Tailwind class
          element.classList.add("bg-surface-yellow-2");

          // Remove highlight after 2 seconds
          setTimeout(() => {
            element.classList.remove("bg-surface-yellow-2");
            router.replace({ hash: "" });
          }, 2000);
        }
      }, 1000);
    });
  }
}

watch(
  () => route.hash,
  () => {
    scrollToLatestActivity();
  }
);

watch(
  () => props.title,
  () => {
    scrollToLatestActivity();
  },
  { immediate: true }
);

defineExpose({
  scrollToLatestActivity,
});
</script>
<style scoped>
.activity:focus {
  outline: none;
}
</style>
