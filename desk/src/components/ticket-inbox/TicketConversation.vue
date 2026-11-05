<template>
  <!-- the ticket as one conversation (Phase 16): the customer's emails left, ours right in blue,
       the team's notes and questions to Copilot right in yellow, Copilot's messages as wide grey
       cards, and what happened as small lines; oldest first, newest at the bottom -->
  <div class="flex min-h-0 flex-1 flex-col bg-surface-gray-1">
    <div
      class="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-outline-gray-1 bg-surface-base px-4 py-1.5 hide-scrollbar sm:px-5"
      role="radiogroup"
      :aria-label="__('Show in the conversation')"
    >
      <button
        v-for="f in FILTERS"
        :key="f.key"
        type="button"
        role="radio"
        :aria-checked="filter === f.key"
        :title="f.hint"
        class="inline-flex h-8 shrink-0 max-sm:h-11 [@media(pointer:coarse)]:h-11 items-center gap-1.5 rounded-full px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        :class="
          filter === f.key
            ? 'bg-surface-gray-3 font-medium text-ink-gray-9'
            : 'text-ink-gray-6 hover:text-ink-gray-9'
        "
        @click="filter = f.key"
      >
        <span
          v-if="f.key === 'customer'"
          class="size-2.5 rounded-full border border-outline-blue-1 bg-surface-blue-2"
          aria-hidden="true"
        />
        <span
          v-else-if="f.key === 'team'"
          class="size-2.5 rounded-full border border-note-border bg-note"
          aria-hidden="true"
        />
        {{ f.label }}
        <span
          v-if="f.key !== 'all'"
          class="font-mono text-2xs tabular-nums text-ink-gray-5"
          >{{ counts[f.key] }}</span
        >
      </button>
    </div>

    <div
      ref="scroller"
      class="min-h-0 flex-1 overflow-y-auto"
      role="log"
      :aria-label="__('Conversation')"
      @scroll.passive="onScroll"
    >
      <div ref="content" class="mx-auto max-w-4xl space-y-4 px-4 py-4 sm:px-6">
        <div
          v-if="!activities?.data && !activities?.error"
          class="space-y-4"
          aria-busy="true"
          :aria-label="__('Loading conversation')"
        >
          <div
            v-for="i in 3"
            :key="i"
            class="h-20 animate-pulse rounded-2xl bg-surface-gray-2"
            :class="i === 2 ? 'ms-auto w-2/3' : 'w-3/4'"
          />
        </div>
        <TaskyState
          v-else-if="activities?.error"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the conversation')"
          :message="errorText(activities.error, __('Check your connection.'))"
          error
        >
          <Button :label="__('Retry')" @click="activities.reload()" />
        </TaskyState>
        <p
          v-else-if="!shown.length"
          class="py-12 text-center text-base text-ink-gray-5"
        >
          {{
            filter === "team"
              ? __("Nothing only for the team yet.")
              : __("Nothing here yet.")
          }}
        </p>

        <template v-for="(e, i) in shown" :key="e.key">
          <div
            v-if="i === 0 || day(e.at) !== day(shown[i - 1].at)"
            class="flex items-center gap-3 pt-1"
            role="separator"
            :aria-label="day(e.at)"
          >
            <span class="h-px flex-1 bg-outline-gray-2" />
            <span class="text-xs font-medium text-ink-gray-5">{{
              day(e.at)
            }}</span>
            <span class="h-px flex-1 bg-outline-gray-2" />
          </div>

          <EmailBubble
            v-if="e.kind === 'email'"
            :activity="e.item"
            :contact-first="contactFirst"
            :ticket-status="doc.status"
            @reply="(target) => emit('reply', target)"
          />

          <!-- the opening request when the ticket has no email of its own (made on the desk) -->
          <article
            v-else-if="e.kind === 'request'"
            class="flex w-full max-w-2xl gap-2.5"
            :aria-label="__('The customer\'s request')"
          >
            <Avatar size="lg" class="mt-6 shrink-0" :label="e.item.who" />
            <div class="min-w-0 flex-1">
              <p class="mb-1 text-sm">
                <span class="font-medium text-ink-gray-9">{{
                  e.item.who
                }}</span>
                <span class="text-ink-gray-5"> · {{ clock(e.at) }}</span>
              </p>
              <div
                class="whitespace-pre-line rounded-2xl rounded-ss-md border border-outline-gray-2 bg-surface-base px-3.5 py-2.5 text-base text-ink-gray-9"
              >
                {{ e.item.text }}
              </div>
            </div>
          </article>

          <div
            v-else-if="e.kind === 'note'"
            :id="e.item.key"
            class="ms-auto flex w-full max-w-2xl"
          >
            <CommentBox
              :activity="e.item"
              @update="() => activities.reload()"
            />
          </div>

          <!-- a person writing to Copilot: the team only -->
          <div
            v-else-if="e.kind === 'ask'"
            class="ms-auto flex max-w-[min(85%,42rem)] flex-col items-end"
          >
            <p
              class="mb-1 flex flex-wrap items-center justify-end gap-x-1.5 text-sm"
            >
              <span
                class="inline-flex items-center gap-1 font-medium text-warning"
              >
                <LucideSparkles class="size-3.5" aria-hidden="true" />
                {{ __("To Copilot · only the team") }}
              </span>
              <span class="text-ink-gray-4" aria-hidden="true">·</span>
              <span class="font-medium text-ink-gray-9">{{
                e.item.author || __("Someone")
              }}</span>
              <span v-if="e.item.via === 'Teams'" class="text-ink-gray-5">{{
                __("in Teams")
              }}</span>
              <time class="text-ink-gray-5">{{ clock(e.at) }}</time>
            </p>
            <div
              class="whitespace-pre-line rounded-2xl rounded-se-md border border-note-border bg-note px-3.5 py-2.5 text-base text-ink-gray-9"
            >
              {{ e.item.text }}
            </div>
          </div>

          <!-- Copilot talking to the team: a wide card, never a bubble to the customer -->
          <section
            v-else-if="e.kind === 'copilot' || e.kind === 'copilotNote'"
            class="mx-auto w-full max-w-3xl rounded-2xl bg-surface-gray-3 px-4 py-3"
            :aria-label="__('From TBO Copilot')"
          >
            <p class="mb-1.5 flex flex-wrap items-center gap-x-1.5 text-sm">
              <LucideSparkles
                class="size-4 text-ink-gray-7"
                aria-hidden="true"
              />
              <span class="font-semibold text-ink-gray-9">{{
                __("TBO Copilot")
              }}</span>
              <Tooltip :text="dateFormat(e.at, dateTooltipFormat)">
                <time class="text-ink-gray-5">{{ clock(e.at) }}</time>
              </Tooltip>
              <span class="inline-flex items-center gap-1 text-ink-gray-5">
                · <LucideLock class="size-3" aria-hidden="true" />
                {{ __("only the team") }}
              </span>
            </p>
            <RichText v-if="e.kind === 'copilotNote'" :html="e.item.content" />
            <CopilotCard
              v-else-if="e.item.card"
              :card="copilot.forThisPerson(e.item.card)"
              :busy="copilot.busy.value"
              :status="e.item.status === 'Done' ? __('Done') : null"
              @press="(a, values) => copilot.press(a, values, e.item.name)"
            />
            <p v-else class="whitespace-pre-line text-base text-ink-gray-8">
              {{ e.item.text }}
            </p>
          </section>

          <!-- what happened: status, assignment, calls, the rating -->
          <div
            v-else
            class="mx-auto flex max-w-xl flex-wrap items-center justify-center gap-x-1.5 px-4 text-center text-sm text-ink-gray-5"
          >
            <component
              :is="e.icon"
              v-if="e.icon"
              class="size-3.5 shrink-0"
              :class="e.iconClass"
              aria-hidden="true"
            />
            <span>
              <span v-if="e.who" class="font-medium text-ink-gray-7">{{
                e.who
              }}</span>
              {{ e.text }}
            </span>
            <button
              v-if="e.more?.length"
              type="button"
              class="rounded text-ink-gray-6 underline underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              :aria-expanded="opened.has(e.key)"
              @click="toggle(e.key)"
            >
              {{
                opened.has(e.key)
                  ? __("less")
                  : __("and {0} more", String(e.more.length))
              }}
            </button>
            <span aria-hidden="true">·</span>
            <Tooltip :text="dateFormat(e.at, dateTooltipFormat)">
              <time>{{ clock(e.at) }}</time>
            </Tooltip>
            <span v-if="opened.has(e.key)" class="basis-full text-ink-gray-6">
              {{ e.more?.join(" · ") }}
            </span>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import CommentBox from "@/components/CommentBox.vue";
import CopilotCard from "@/components/copilot/CopilotCard.vue";
import type { ReplyTarget } from "@/components/emailReply";
import TaskyState from "@/components/TaskyState.vue";
import { ticketRequest } from "@/components/ticket-agent/ticketRequest";
import { useTicketActivities } from "@/composables/useTicketActivities";
import { __ } from "@/translation";
import { ActivitiesSymbol, TicketSymbol } from "@/types";
import { dateFormat, dateTooltipFormat, errorText } from "@/utils";
import { Avatar, Button, dayjsLocal, Tooltip } from "frappe-ui";
import {
  computed,
  inject,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
  type Component,
} from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideLock from "~icons/lucide/lock";
import LucidePhoneIncoming from "~icons/lucide/phone-incoming";
import LucidePhoneOutgoing from "~icons/lucide/phone-outgoing";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideStar from "~icons/lucide/star";
import EmailBubble from "./EmailBubble.vue";
import { firstName } from "./inbox";
import RichText from "./RichText.vue";
import { useCopilotThread, type ThreadMessage } from "./useCopilotThread";

const emit = defineEmits<{ reply: [target: ReplyTarget] }>();

const ticket = inject(TicketSymbol)!;
const activitiesRef = inject(ActivitiesSymbol)!;
const activities = computed(() => activitiesRef.value);
const doc = computed(() => ticket.value.doc);
const contactFirst = computed(() =>
  firstName(doc.value.contact || doc.value.raised_by)
);
// the ticket page re-mounts this per ticket (TicketAgent keys it)
const copilot = useCopilotThread(String(doc.value.name));
const { activities: timeline } = useTicketActivities(activitiesRef, doc);

type Filter = "all" | "customer" | "team";
const FILTERS: { key: Filter; label: string; hint: string }[] = [
  {
    key: "all",
    label: __("Everything"),
    hint: __("Messages, notes, Copilot and what happened"),
  },
  {
    key: "customer",
    label: __("Customer sees"),
    hint: __("What went to and came from the customer"),
  },
  {
    key: "team",
    label: __("Team only"),
    hint: __("Notes and Copilot: the customer never sees these"),
  },
];
const filter = ref<Filter>("all");

type Entry = {
  key: string;
  at: string;
  kind:
    | "email"
    | "request"
    | "note"
    | "copilotNote"
    | "ask"
    | "copilot"
    | "event";
  /** who sees it: the customer too, or the team only */
  audience: "customer" | "team" | "none";
  item?: any;
  who?: string;
  text?: string;
  more?: string[];
  icon?: Component;
  iconClass?: string;
};

const VIEWED = "viewed this";

const entries = computed<Entry[]>(() => {
  const out: Entry[] = [];
  let emails = 0;
  for (const a of timeline.value as any[]) {
    if (a.type === "email") {
      emails++;
      out.push({
        key: a.key,
        at: a.creation,
        kind: "email",
        audience: "customer",
        item: a,
      });
    } else if (a.type === "comment") {
      out.push({
        key: a.key,
        at: a.creation,
        kind: a.byAutomation ? "copilotNote" : "note",
        audience: "team",
        item: a,
      });
    } else if (a.type === "call") {
      out.push({
        key: a.key,
        at: a.creation,
        kind: "event",
        audience: "customer",
        text: `${a.content} · ${a.duration}`,
        icon:
          a.call_type === "Incoming"
            ? LucidePhoneIncoming
            : LucidePhoneOutgoing,
      });
    } else if (a.type === "feedback") {
      const stars = Math.round(
        Number(a.feedback_rating) <= 1
          ? Number(a.feedback_rating) * 5
          : Number(a.feedback_rating)
      );
      const words = [a.feedback, a.feedback_extra].filter(Boolean).join(": ");
      out.push({
        key: a.key,
        at: doc.value.modified,
        kind: "event",
        audience: "customer",
        who: a.sender?.full_name || contactFirst.value,
        text: words
          ? __("rated it {0}/5: {1}", String(stars), words)
          : __("rated it {0}/5", String(stars)),
        icon: LucideStar,
        iconClass: "text-warning",
      });
    } else if (a.type === "history" && a.content !== VIEWED) {
      const more = (a.relatedActivities || [])
        .slice(1)
        .map((r: any) => r.content)
        .filter((c: string) => c && c !== VIEWED);
      out.push({
        key: a.key,
        at: a.creation,
        kind: "event",
        audience: "none",
        who: String(a.user || "").trim(),
        text: a.content,
        more,
      });
    }
  }
  // a ticket made on the desk has no email of its own: its description opens the thread
  if (!emails && activities.value?.data) {
    const request = ticketRequest(doc.value);
    if (request?.text)
      out.push({
        key: "request",
        at: request.at,
        kind: "request",
        audience: "customer",
        item: request,
      });
  }
  for (const m of copilot.messages.value as ThreadMessage[]) {
    if (m.direction === "In")
      out.push({
        key: m.name,
        at: m.at,
        kind: "ask",
        audience: "team",
        item: m,
      });
    else if (m.card?.tone === "note")
      out.push({
        key: m.name,
        at: m.at,
        kind: "event",
        audience: "none",
        text: (m.card.lines || []).join(" "),
        icon: LucideSparkles,
      });
    else
      out.push({
        key: m.name,
        at: m.at,
        kind: "copilot",
        audience: "team",
        item: m,
      });
  }
  return out.sort(
    (x, y) => dayjsLocal(x.at).valueOf() - dayjsLocal(y.at).valueOf()
  );
});

const shown = computed(() =>
  filter.value === "all"
    ? entries.value
    : entries.value.filter((e) => e.audience === filter.value)
);
const counts = computed(() => ({
  customer: entries.value.filter((e) => e.audience === "customer").length,
  team: entries.value.filter((e) => e.audience === "team").length,
}));

const opened = reactive(new Set<string>());
function toggle(key: string) {
  if (opened.has(key)) opened.delete(key);
  else opened.add(key);
}

function clock(at: string) {
  return dayjsLocal(at).format("h:mm A");
}

function day(at: string) {
  const d = dayjsLocal(at);
  const today = dayjsLocal();
  if (d.isSame(today, "day")) return __("Today");
  if (d.isSame(today.subtract(1, "day"), "day")) return __("Yesterday");
  return d.format(d.year() === today.year() ? "ddd D MMM" : "D MMM YYYY");
}

// --- the newest message stays in sight --------------------------------------------------------
const scroller = ref<HTMLElement | null>(null);
const content = ref<HTMLElement | null>(null);
const atBottom = ref(true);

function onScroll() {
  const el = scroller.value;
  if (el)
    atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
}

function toBottom(smooth = false) {
  const el = scroller.value;
  if (el)
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
}

watch(
  () => shown.value.length,
  async (now, before) => {
    await nextTick();
    // a new message: follow it if the agent was at the bottom (or it's the first load)
    if (atBottom.value || !before) toBottom(Boolean(before));
  }
);
watch(filter, async () => {
  await nextTick();
  toBottom();
});

// emails render in frames that size themselves after loading: stay at the bottom while they do
let keep: ResizeObserver | null = null;
onMounted(() => {
  toBottom();
  keep = new ResizeObserver(() => atBottom.value && toBottom());
  if (scroller.value) keep.observe(scroller.value);
  if (content.value) keep.observe(content.value);
});
onBeforeUnmount(() => keep?.disconnect());
</script>
