<template>
  <div v-if="matches.length">
    <DuplicateLeadsNotice
      :matches="matches"
      :title="__('This may be the same person as another lead')"
      can-merge
      @merge="openMerge"
    />
    <MergeLeadsDialog
      v-model:open="showMerge"
      :first="lead.name"
      :second="other"
      @merged="done"
    />
  </div>
</template>

<script setup lang="ts">
import { call } from "frappe-ui";
import { ref, watch } from "vue";
import DuplicateLeadsNotice from "./DuplicateLeadsNotice.vue";
import {
  isUsable,
  type DuplicateLead,
  type LeadDetail,
  type LeadNumber,
} from "./leads";
import MergeLeadsDialog from "./MergeLeadsDialog.vue";

/** Other leads that share this lead's email or a number, for a manager to merge in. */
const props = defineProps<{ lead: LeadDetail["lead"] }>();
const emit = defineEmits<{ (e: "merged", keep: string): void }>();

const MAX_NUMBERS = 3;
const matches = ref<DuplicateLead[]>([]);
const other = ref("");
const showMerge = ref(false);
let asked = 0;

function phones(): string[] {
  const numbers = ((props.lead.numbers ?? []) as LeadNumber[])
    .filter(isUsable)
    .map((n) => n.number);
  return (numbers.length ? numbers : [props.lead.mobile_no || ""])
    .filter(Boolean)
    .slice(0, MAX_NUMBERS);
}

async function find() {
  const asking = ++asked;
  const email = props.lead.email_id || "";
  const numbers = phones();
  // find_duplicate_leads takes one number: ask for each, the email with the first
  const questions = (numbers.length ? numbers : [""]).map(
    (phone, i): Promise<{ matches?: DuplicateLead[] }> =>
      call("helpdesk.api.leads.find_duplicate_leads", {
        email: i === 0 ? email : "",
        phone,
        exclude: props.lead.name,
      }).then(
        (answer: unknown) => answer as { matches?: DuplicateLead[] },
        () => ({ matches: [] })
      )
  );
  const answers = await Promise.all(questions);
  if (asking !== asked) return;
  const found = new Map<string, DuplicateLead>();
  for (const match of answers.flatMap((a) => a.matches ?? [])) {
    const seen = found.get(match.name);
    found.set(match.name, {
      ...match,
      matched_on: [
        ...new Set([...(seen?.matched_on ?? []), ...match.matched_on]),
      ],
    });
  }
  matches.value = [...found.values()];
}

function done(keep: string) {
  // the merged lead is gone from the list
  find();
  emit("merged", keep);
}

function openMerge(match: DuplicateLead) {
  other.value = match.name;
  showMerge.value = true;
}

watch(() => [props.lead.name, props.lead.email_id, phones().join("|")], find, {
  immediate: true,
});
</script>
