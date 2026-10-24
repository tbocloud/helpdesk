<template>
  <!-- where the proposal is with the client; nothing to show before it's sent -->
  <section
    v-if="t.sent_on || t.decided_on"
    class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
    :aria-label="__('With the client')"
  >
    <dl class="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <div class="flex flex-col gap-0.5">
        <dt class="text-xs text-ink-gray-5">{{ __("Sent") }}</dt>
        <dd class="text-sm tabular-nums text-ink-gray-8">
          {{ when(t.sent_on) }}
        </dd>
        <dd
          v-if="t.sent_to"
          class="truncate font-mono text-xs text-ink-gray-6"
          :title="t.sent_to"
        >
          {{ t.sent_to }}
        </dd>
      </div>
      <div class="flex flex-col gap-0.5">
        <dt class="text-xs text-ink-gray-5">{{ __("Views") }}</dt>
        <dd
          class="flex items-center gap-1.5 font-mono text-sm tabular-nums text-ink-gray-8"
        >
          <LucideEye class="size-4 text-ink-gray-5" aria-hidden="true" />
          {{ t.view_count || 0 }}
        </dd>
      </div>
      <div class="flex flex-col gap-0.5">
        <dt class="text-xs text-ink-gray-5">{{ __("Last opened") }}</dt>
        <dd class="text-sm tabular-nums text-ink-gray-8">
          {{ t.last_viewed_on ? when(t.last_viewed_on) : __("Not yet") }}
        </dd>
      </div>
      <div class="flex flex-col gap-0.5">
        <dt class="text-xs text-ink-gray-5">
          {{
            proposal.status === "Declined"
              ? __("Declined")
              : proposal.accepted_label || __("Accepted")
          }}
        </dt>
        <dd v-if="t.decided_on" class="text-sm tabular-nums text-ink-gray-8">
          {{ when(t.decided_on) }}
        </dd>
        <dd v-else class="text-sm text-ink-gray-6">{{ __("Not yet") }}</dd>
        <dd v-if="t.decided_by_name" class="text-xs text-ink-gray-6">
          {{ t.decided_by_name }}
          <template v-if="t.decided_by_designation">
            ({{ t.decided_by_designation }})</template
          >
          <span v-if="t.decided_by_email" class="font-mono">
            · {{ t.decided_by_email }}</span
          >
        </dd>
      </div>
    </dl>
    <p
      v-if="t.decline_reason"
      class="mt-3 rounded-md bg-surface-gray-1 px-3 py-2 text-p-sm text-ink-gray-7"
    >
      {{ __("Their reason: {0}", t.decline_reason) }}
    </p>
    <div
      v-if="proposal.public_url"
      class="mt-3 flex flex-wrap items-center gap-2 border-t border-outline-gray-1 pt-3"
    >
      <span class="text-xs text-ink-gray-5">{{ __("Client's link") }}</span>
      <code class="min-w-0 flex-1 truncate font-mono text-xs text-ink-gray-7">{{
        proposal.public_url
      }}</code>
      <Button size="sm" :label="__('Copy link')" @click="copy">
        <template #prefix>
          <LucideCopy class="size-3.5" aria-hidden="true" />
        </template>
      </Button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, dayjs, toast } from "frappe-ui";
import { computed } from "vue";
import LucideCopy from "~icons/lucide/copy";
import LucideEye from "~icons/lucide/eye";
import type { Proposal } from "./proposals";

const props = defineProps<{ proposal: Proposal }>();
const t = computed(() => props.proposal.tracking);

function when(at?: string | null) {
  return at ? dayjs(at).format("D MMM YYYY, h:mm a") : "";
}

async function copy() {
  try {
    await navigator.clipboard.writeText(props.proposal.public_url || "");
    toast.success(__("Link copied"));
  } catch {
    toast.error(__("Couldn't copy. Select the link and copy it."));
  }
}
</script>
