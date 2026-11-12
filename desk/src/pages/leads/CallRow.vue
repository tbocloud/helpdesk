<template>
  <!-- the call to make now: who, how to reach them, what to say, how it went -->
  <section
    :aria-labelledby="titleId"
    class="rounded-xl border bg-surface-base p-4 sm:p-6"
    :class="overdue ? 'border-danger' : 'border-outline-gray-2'"
  >
    <p class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-6">
      <span v-if="position" class="tabular-nums">{{ position }}</span>
      <TaskyBadge
        v-if="overdue"
        tone="danger"
        :icon="LucideAlarmClock"
        :label="__('Overdue')"
      />
      <TaskyBadge
        v-else-if="call.reason"
        :icon="LucideInfo"
        :label="call.reason"
      />
      <TaskyBadge
        v-if="call.summary.temperature === 'Hot'"
        tone="warning"
        :icon="LucideFlame"
        :label="__('Hot')"
      />
    </p>
    <h2
      :id="titleId"
      class="mt-1.5 text-2xl font-semibold text-ink-gray-9 sm:text-3xl"
    >
      <span v-if="readOnly">{{ name }}</span>
      <router-link
        v-else
        :to="{ name: 'Lead', params: { leadId: call.lead } }"
        class="rounded hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        >{{ name }}</router-link
      >
    </h2>
    <p v-if="meta" class="mt-1 text-p-base text-ink-gray-7">{{ meta }}</p>

    <!-- the one big action: MyOperator rings the person's phone, else the phone dials -->
    <div v-if="!readOnly" class="mt-5 flex flex-wrap items-center gap-3">
      <button
        v-if="canCall"
        type="button"
        :class="CALL_BUTTON"
        :disabled="dialing"
        :aria-label="__('Call {0}', name)"
        @click="emit('dial', call)"
      >
        <LucideLoaderCircle
          v-if="dialing"
          class="size-5 animate-spin"
          aria-hidden="true"
        />
        <LucidePhone v-else class="size-5" aria-hidden="true" />
        {{ __("Call") }}
        <span class="font-mono tabular-nums">{{ call.summary.phone }}</span>
      </button>
      <a
        v-else-if="dialable"
        :href="`tel:${dialable}`"
        :class="CALL_BUTTON"
        :aria-label="__('Call {0}', name)"
        @click="emit('dialed', call)"
      >
        <LucidePhone class="size-5" aria-hidden="true" />
        {{ __("Call") }}
        <span class="font-mono tabular-nums">{{ call.summary.phone }}</span>
      </a>
      <Button
        v-if="whatsapp"
        size="xl"
        class="max-sm:w-full"
        :link="`https://wa.me/${whatsapp}`"
        target="_blank"
        :label="__('WhatsApp')"
        :aria-label="__('WhatsApp {0}', name)"
      >
        <template #prefix>
          <LucideMessageCircle class="size-5" aria-hidden="true" />
        </template>
      </Button>
    </div>
    <div v-if="others.length" class="mt-2 flex flex-col gap-1">
      <button
        type="button"
        class="inline-flex min-h-8 items-center gap-1 self-start rounded text-p-sm text-ink-gray-7 underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        :aria-expanded="showOthers"
        @click="showOthers = !showOthers"
      >
        {{
          others.length === 1
            ? __("1 more number")
            : __("{0} more numbers", String(others.length))
        }}
        <component
          :is="showOthers ? LucideChevronUp : LucideChevronDown"
          class="size-3.5"
          aria-hidden="true"
        />
      </button>
      <ul v-if="showOthers" role="list" class="flex flex-col gap-1">
        <li
          v-for="other in others"
          :key="other.id"
          class="flex items-center gap-2"
        >
          <span class="min-w-0 flex-1">
            <span class="font-mono text-sm tabular-nums text-ink-gray-8">{{
              other.number
            }}</span>
            <span class="text-p-xs text-ink-gray-6">
              · {{ other.person || other.label }}</span
            >
          </span>
          <template v-if="readOnly" />
          <Button
            v-else-if="canCall"
            variant="subtle"
            :label="__('Call')"
            :aria-label="__('Call {0}', other.number)"
            @click="emit('dial', call, other.number)"
          >
            <template #prefix>
              <LucidePhone class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <Button
            v-else
            variant="subtle"
            :link="`tel:${dialNumber(other.number)}`"
            :label="__('Call')"
            :aria-label="__('Call {0}', other.number)"
            @click="emit('dialed', call, other.number)"
          >
            <template #prefix>
              <LucidePhone class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </li>
      </ul>
    </div>

    <!-- what to say you are calling under: the product, else the department -->
    <div
      v-if="call.calling_for || call.intro_line"
      class="mt-5 rounded-lg bg-surface-gray-1 px-4 py-3.5"
    >
      <p
        class="flex min-w-0 items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-ink-gray-6"
      >
        <LucideBox class="size-3.5 shrink-0" aria-hidden="true" />
        <span class="truncate">{{
          call.calling_for
            ? __("Calling for: {0}", call.calling_for)
            : __("Say first")
        }}</span>
      </p>
      <p v-if="call.intro_line" class="mt-1.5 text-p-base text-ink-gray-8">
        <span v-if="call.calling_for" class="sr-only"
          >{{ __("Say first") }}: </span
        >{{ call.intro_line }}
      </p>
    </div>

    <template v-if="!readOnly">
      <h3 class="mb-2.5 mt-6 text-base-medium text-ink-gray-9">
        {{ __("How did it go?") }}
      </h3>
      <div
        class="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-2.5"
        role="group"
        :aria-label="__('How did the call with {0} go?', name)"
      >
        <button
          v-for="chip in CHIPS"
          :key="chip.value"
          type="button"
          class="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg border border-outline-gray-2 bg-surface-base px-3 text-sm text-ink-gray-8 transition-colors hover:border-brand hover:bg-brand-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          @click="emit('outcome', call, chip.value, note.trim())"
        >
          <component :is="chip.icon" class="size-4" aria-hidden="true" />
          {{ chip.label }}
        </button>
      </div>
      <div class="mt-4">
        <FormControl
          v-model="note"
          type="textarea"
          :rows="3"
          maxlength="500"
          :label="__('Note (optional)')"
          :placeholder="__('What did they say?')"
        />
      </div>
    </template>

    <div
      v-if="call.summary.last_note || call.summary.next_step"
      class="mt-4 flex flex-col gap-1.5"
    >
      <p
        v-if="call.summary.last_note"
        class="line-clamp-2 text-p-sm text-ink-gray-6"
      >
        <span class="font-medium">{{ __("Last note") }}:</span>
        {{ call.summary.last_note }}
      </p>
      <p
        v-if="call.summary.next_step"
        class="line-clamp-2 flex items-start gap-1 text-p-sm text-ink-gray-7"
      >
        <LucideSparkles
          class="mt-0.5 size-3.5 shrink-0 text-ink-gray-5"
          aria-hidden="true"
        />
        <span>
          <span class="sr-only">{{ __("AI suggests") }}: </span
          >{{ call.summary.next_step }}
        </span>
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { Button, FormControl } from "frappe-ui";
import { computed, ref, useId } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronUp from "~icons/lucide/chevron-up";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideBox from "~icons/lucide/box";
import LucideFlame from "~icons/lucide/flame";
import LucideInfo from "~icons/lucide/info";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucideMessageCircle from "~icons/lucide/message-circle";
import LucidePhone from "~icons/lucide/phone";
import LucideSparkles from "~icons/lucide/sparkles";
import {
  dialNumber,
  OUTCOME_LOOK,
  OUTCOMES,
  type CallOutcome,
  type QueueCall,
} from "./callBatches";

const props = defineProps<{
  call: QueueCall;
  canCall: boolean;
  dialing?: boolean;
  overdue?: boolean;
  /** "Call 3 of 14": where this one is in the queue */
  position?: string;
  /** someone else's call, watched: nothing to dial or answer */
  readOnly?: boolean;
}>();
const emit = defineEmits<{
  // `number`: one of the lead's other numbers; none: the main one
  (e: "dial", call: QueueCall, number?: string): void;
  // the phone's own dialler was used: a result is expected when the person is back
  (e: "dialed", call: QueueCall, number?: string): void;
  // `note`: what was typed on the card (may be empty)
  (e: "outcome", call: QueueCall, outcome: CallOutcome, note: string): void;
}>();

const titleId = `call-now-${useId()}`;
// the primary button, as a frappe-ui solid one: at least 48px tall for a thumb
const CALL_BUTTON =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-lg bg-brand px-5 text-base-medium text-brand-on transition-colors hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight focus-visible:ring-offset-2 disabled:opacity-60 max-sm:w-full";

const CHIPS = OUTCOMES.map((o) => ({ ...o, icon: OUTCOME_LOOK[o.value].icon }));

const note = ref("");
const name = computed(
  () =>
    props.call.summary.lead_name || props.call.summary.name || props.call.lead
);
const meta = computed(() =>
  [
    props.call.summary.company_name,
    props.call.summary.industry,
    props.call.summary.district,
  ]
    .filter(Boolean)
    .join(" · ")
);
const dialable = computed(() => dialNumber(props.call.summary.phone));
// wa.me takes the number with its country code and no "+"
const whatsapp = computed(() => dialable.value.replace(/\D/g, ""));
// the lead's other numbers still in use, behind "+1 more"
const others = computed(() => props.call.summary.other_numbers ?? []);
const showOthers = ref(false);
</script>
