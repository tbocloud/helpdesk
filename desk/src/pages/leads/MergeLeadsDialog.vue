<template>
  <Dialog
    :open="open"
    :title="__('Merge leads')"
    size="2xl"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <TaskyState
      v-if="preview.error && !sides.length"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t open these leads')"
      :message="
        errorText(preview.error, __('Check your connection and try again.'))
      "
    >
      <Button :label="__('Try again')" @click="preview.reload()" />
    </TaskyState>

    <div
      v-else-if="!sides.length"
      class="grid grid-cols-1 gap-3 sm:grid-cols-2"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div
        v-for="n in 2"
        :key="n"
        class="h-48 animate-pulse rounded-lg border border-outline-gray-2 bg-surface-gray-1"
      />
    </div>

    <form
      v-else
      :id="formId"
      class="flex flex-col gap-4"
      @submit.prevent="submit"
    >
      <fieldset class="flex flex-col gap-2">
        <legend class="mb-1 text-p-sm text-ink-gray-7">
          {{ __("Same person twice? Choose the lead to keep.") }}
        </legend>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label
            v-for="side in sides"
            :key="side.name"
            class="flex min-h-11 cursor-pointer flex-col gap-2 rounded-lg border border-outline-gray-2 p-3 focus-within:ring-2 focus-within:ring-highlight"
            :class="keep === side.name ? 'bg-brand-soft' : 'bg-surface-base'"
          >
            <span class="flex items-center gap-2">
              <input
                v-model="keep"
                type="radio"
                name="lead-to-keep"
                :value="side.name"
                class="size-4 border-outline-gray-4 text-ink-gray-9 focus-visible:outline-none"
              />
              <span class="text-base-medium text-ink-gray-9">
                {{ __("Keep this one") }}
              </span>
            </span>
            <span class="flex flex-col gap-0.5 break-words">
              <span class="text-base-medium text-ink-gray-9">{{
                side.lead_name || side.name
              }}</span>
              <span
                v-if="side.company_name"
                class="text-p-sm text-ink-gray-7"
                >{{ side.company_name }}</span
              >
              <span class="font-mono text-p-xs tabular-nums text-ink-gray-6">{{
                side.name
              }}</span>
            </span>
            <span class="flex flex-wrap items-center gap-1.5">
              <TaskyBadge
                v-if="side.tbo_stage"
                :label="stageLabel(options, side.tbo_stage)"
                :tone="stageTone(options, side.tbo_stage)"
                :icon="stageIcon(side.tbo_stage)"
              />
            </span>
            <dl class="flex flex-col gap-1 text-p-sm text-ink-gray-7">
              <div v-if="side.email_id" class="break-all">
                {{ side.email_id }}
              </div>
              <div
                v-for="n in side.numbers.filter(isUsable)"
                :key="n.id"
                class="font-mono tabular-nums"
              >
                {{ n.number }}
              </div>
              <div v-if="side.owner_name || side.lead_owner">
                {{ __("Owner: {0}", side.owner_name || side.lead_owner || "") }}
              </div>
              <div>
                {{ __("Added {0}", dayjs(side.creation).format("D MMM YYYY")) }}
              </div>
            </dl>
          </label>
        </div>
      </fieldset>

      <div
        role="status"
        class="flex flex-col gap-1 rounded-md bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-8"
      >
        <p>{{ movesText }}</p>
        <p class="text-ink-gray-7">
          {{
            __(
              "{0} is removed after this and can't be brought back. Its notes, calls and numbers stay on {1}.",
              labelOf(merged),
              labelOf(kept)
            )
          }}
        </p>
      </div>

      <p v-if="errorMessage" role="alert" class="text-p-sm text-danger">
        {{ errorMessage }}
      </p>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Merge into {0}', labelOf(kept))"
          :disabled="sides.length !== 2"
          :loading="merge.loading"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs, Dialog, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import {
  isUsable,
  leadOptions,
  stageIcon,
  stageLabel,
  stageTone,
  type LeadOptions,
  type MergeCount,
  type MergeLead,
} from "./leads";

const props = defineProps<{
  open: boolean;
  /** the two leads to merge, in any order */
  first: string;
  second: string;
}>();
const emit = defineEmits<{
  (e: "update:open", value: boolean): void;
  /** `keep` is the lead that is left */
  (e: "merged", keep: string): void;
}>();

const formId = `merge-leads-${useId()}`;
const options = computed(() => leadOptions.data as LeadOptions | undefined);
const keep = ref("");
const errorMessage = ref("");

const preview = createResource({
  url: "helpdesk.api.leads.get_merge_preview",
  makeParams: () => ({ first: props.first, second: props.second }),
  onSuccess(data: { leads: MergeLead[] }) {
    keep.value = defaultKeep(data.leads);
  },
});
const sides = computed<MergeLead[]>(
  () => (preview.data as { leads: MergeLead[] } | undefined)?.leads ?? []
);
const kept = computed(() => sides.value.find((s) => s.name === keep.value));
const merged = computed(() => sides.value.find((s) => s.name !== keep.value));

watch(
  () => props.open,
  (open) => {
    if (!open || !props.first || !props.second) return;
    errorMessage.value = "";
    keep.value = "";
    preview.reset();
    preview.fetch();
  },
  { immediate: true }
);

/** The lead further along the pipeline (a lost stage counts last), else the older one. */
function defaultKeep(leads: MergeLead[]): string {
  const rank = (lead: MergeLead) => {
    const stages = options.value?.stages ?? [];
    const stage = stages.find((s) => s.name === lead.tbo_stage);
    return !stage || stage.type === "Lost" ? -1 : stages.indexOf(stage);
  };
  const [a, b] = leads as [MergeLead, MergeLead];
  if (rank(a) !== rank(b)) return (rank(a) > rank(b) ? a : b).name;
  return (dayjs(a.creation).isAfter(b.creation) ? b : a).name;
}

function labelOf(lead?: MergeLead) {
  return lead?.lead_name || lead?.name || "";
}

const NOUNS: Record<MergeCount | "numbers", [string, string]> = {
  notes: [__("note"), __("notes")],
  calls: [__("call"), __("calls")],
  numbers: [__("number"), __("numbers")],
  quotations: [__("quotation"), __("quotations")],
  proposals: [__("proposal"), __("proposals")],
  deals: [__("deal"), __("deals")],
  meetings: [__("meeting"), __("meetings")],
  follow_ups: [__("follow-up"), __("follow-ups")],
  files: [__("file"), __("files")],
};

/** "12 notes, 4 calls, 2 numbers will move to Ashraf." */
const movesText = computed(() => {
  const from = merged.value;
  if (!from || !kept.value) return "";
  const counts = { ...from.counts, numbers: from.new_numbers };
  const parts = (Object.keys(NOUNS) as (keyof typeof NOUNS)[])
    .filter((key) => counts[key] > 0)
    .map((key) => `${counts[key]} ${NOUNS[key][counts[key] === 1 ? 0 : 1]}`);
  return parts.length
    ? __("{0} will move to {1}.", parts.join(", "), labelOf(kept.value))
    : __("{0} has nothing else to move.", labelOf(from));
});

const merge = createResource({
  url: "helpdesk.api.leads.merge_leads",
  method: "POST",
  onSuccess() {
    toast.success(__("Merged into {0}", labelOf(kept.value)));
    emit("update:open", false);
    emit("merged", keep.value);
  },
  onError(e: unknown) {
    errorMessage.value = errorText(
      e,
      __("Couldn't merge these leads. Try again.")
    );
  },
});

function submit() {
  if (merge.loading || !kept.value || !merged.value) return;
  errorMessage.value = "";
  merge.submit({ keep: kept.value.name, merge: merged.value.name });
}
</script>
