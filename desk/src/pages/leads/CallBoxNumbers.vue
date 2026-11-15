<template>
  <section class="flex flex-col gap-2" :aria-labelledby="titleId">
    <h3 :id="titleId" class="text-base-medium text-ink-gray-9">
      {{ __("Numbers") }}
    </h3>
    <p v-if="hint" class="text-p-sm text-ink-gray-7">{{ hint }}</p>
    <p v-if="!numbers" class="text-p-sm text-ink-gray-6">
      {{ __("Loading the numbers…") }}
    </p>
    <ul v-else role="list" class="flex flex-col gap-2">
      <li v-for="n in numbers" :key="n.id" class="flex flex-col gap-2">
        <div
          class="flex min-h-14 items-center gap-3 rounded-lg border px-3 py-2"
          :class="
            isDialled(n)
              ? 'border-outline-gray-4 bg-surface-gray-1'
              : 'border-outline-gray-2'
          "
        >
          <div class="flex min-w-0 flex-1 flex-col">
            <span class="font-mono text-base tabular-nums text-ink-gray-9">{{
              n.number
            }}</span>
            <span class="truncate text-p-sm text-ink-gray-6">{{
              about(n)
            }}</span>
          </div>
          <span
            v-if="isDialled(n) && inProgress"
            class="flex shrink-0 items-center gap-1 text-sm text-ink-gray-8"
          >
            <LucideCheck class="size-4" aria-hidden="true" />
            {{ __("Calling this number") }}
          </span>
          <Button
            v-else
            class="!h-11 shrink-0"
            :disabled="!canDial"
            :aria-label="
              isDialled(n)
                ? __('Call {0} again', n.number)
                : __('Call {0}', n.number)
            "
            @click="tap(n)"
          >
            <template #prefix>
              <LucidePhone class="size-4" aria-hidden="true" />
            </template>
            {{ isDialled(n) ? __("Call again") : __("Call") }}
          </Button>
        </div>
        <!-- a call is still on: nothing is hung up for the person -->
        <div
          v-if="confirming === n.id"
          role="alert"
          class="flex flex-col gap-2 rounded-lg bg-surface-gray-2 p-3"
        >
          <p class="flex items-start gap-2 text-sm text-ink-gray-9">
            <LucidePhone
              class="mt-0.5 size-4 shrink-0 text-ink-gray-7"
              aria-hidden="true"
            />
            {{ __("This call is still on. Hang up on your phone first.") }}
          </p>
          <div class="flex flex-wrap gap-2">
            <Button
              class="!h-11"
              :label="__('Call {0} now', n.number)"
              @click="dial(n)"
            />
            <Button
              class="!h-11"
              variant="ghost"
              :label="__('Cancel')"
              @click="confirming = ''"
            />
          </div>
        </div>
      </li>
    </ul>
    <p v-if="!canDial && numbers" class="text-p-sm text-ink-gray-6">
      {{ __("Record the result of this call before you call another number.") }}
    </p>
    <Button
      class="!h-11 self-start"
      variant="ghost"
      :label="__('Add number')"
      @click="emit('add')"
    >
      <template #prefix>
        <LucidePlus class="size-4" aria-hidden="true" />
      </template>
    </Button>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button } from "frappe-ui";
import { ref, useId } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucidePhone from "~icons/lucide/phone";
import LucidePlus from "~icons/lucide/plus";
import { isDialled } from "./callBox";
import type { LeadNumber } from "./leads";

const props = defineProps<{
  /** the lead's usable numbers; undefined while they are being read */
  numbers: LeadNumber[] | undefined;
  /** a call is waiting to connect or on: the dialled number says so, and another asks first */
  inProgress: boolean;
  canDial: boolean;
  /** plain words above the list, e.g. when the call didn't connect */
  hint?: string;
}>();
const emit = defineEmits<{
  (e: "dial", number: LeadNumber): void;
  (e: "add"): void;
}>();

const titleId = useId();
const confirming = ref("");

/** "Decision-maker · Anil", the label and person that tell numbers apart */
function about(n: LeadNumber) {
  return [n.label, n.person].filter(Boolean).join(" · ");
}

function tap(n: LeadNumber) {
  if (props.inProgress) confirming.value = n.id;
  else dial(n);
}

function dial(n: LeadNumber) {
  confirming.value = "";
  emit("dial", n);
}
</script>
