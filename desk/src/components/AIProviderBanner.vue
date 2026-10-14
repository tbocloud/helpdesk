<template>
  <div
    v-if="notice"
    :role="notice.tone === 'danger' ? 'alert' : 'status'"
    class="flex flex-wrap items-start gap-3 rounded-lg p-3"
    :class="TRACK[notice.tone]"
  >
    <component
      :is="notice.icon"
      class="mt-0.5 size-4 shrink-0"
      :class="INK[notice.tone]"
      aria-hidden="true"
    />
    <div class="flex min-w-0 flex-1 flex-col gap-0.5">
      <span class="break-words text-p-sm font-medium text-ink-gray-8">
        {{ notice.title }}
      </span>
      <span class="break-words text-p-sm text-ink-gray-7">
        {{ notice.message }}
        <time
          v-if="down"
          :datetime="down.since"
          :title="dateFormat(down.since, dateTooltipFormat)"
          class="text-ink-gray-6"
        >
          {{ __("Failing since {0}.", dateFormat(down.since, "D MMM, HH:mm")) }}
        </time>
      </span>
    </div>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { INK, TRACK, type Tone } from "@/components/tone";
import { __ } from "@/translation";
import { dateFormat, dateTooltipFormat } from "@/utils";
import { computed, type Component } from "vue";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideInfo from "~icons/lucide/info";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import { providerLabel, type ProviderStatus } from "./aiProviders";

/**
 * Says when the primary AI provider is failing and which provider answers
 * instead; with `showSetup`, also when the primary isn't set up yet.
 * Renders nothing while the primary works.
 */
const props = defineProps<{ status: ProviderStatus; showSetup?: boolean }>();

interface Notice {
  tone: Tone;
  icon: Component;
  title: string;
  message: string;
}

const primary = computed(() => props.status.providers[props.status.primary]);
const down = computed(() => primary.value?.down ?? null);

const notice = computed<Notice | null>(() => {
  const status = props.status;
  const label = providerLabel(status, status.primary);
  const fallback =
    status.in_use && status.in_use !== status.primary
      ? providerLabel(status, status.in_use)
      : null;

  if (primary.value?.configured && (down.value || primary.value.paused)) {
    const title = __("{0} is failing: {1}", label, down.value?.reason || "");
    if (fallback)
      return {
        tone: "warning",
        icon: LucideTriangleAlert,
        title,
        message: __("{0} is answering until it works again.", fallback),
      };
    return {
      tone: "danger",
      icon: LucideCircleX,
      title,
      message: status.in_use
        ? __("AI features may fail until it works again.")
        : __(
            "AI triage, drafts and summaries are paused: no other provider is set up."
          ),
    };
  }

  if (props.showSetup && !primary.value?.configured)
    return {
      tone: "info",
      icon: LucideInfo,
      title: __("{0} isn't set up yet", status.primary),
      message: fallback
        ? __("{0} answers until you add its API key and model.", fallback)
        : __(
            "Add an API key and model to turn on AI triage, drafts and summaries."
          ),
    };
  return null;
});
</script>
