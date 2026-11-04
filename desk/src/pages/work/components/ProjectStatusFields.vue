<template>
  <!-- the fields of one status update; the person's dialog and every row of the review
       table edit the same thing -->
  <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
    <FormControl
      v-model="draft.stage"
      type="select"
      :label="__('Stage')"
      :options="stageOptions"
    />
    <FormControl
      v-model="draft.waiting_on"
      type="select"
      :label="__('Waiting on')"
      :options="waitingOptions"
    />
    <TextInput
      v-if="draft.waiting_on !== NOTHING"
      v-model="draft.waiting_since"
      type="date"
      :label="__('Waiting since')"
      class="sm:col-span-2"
    />
    <FormControl
      v-model="draft.update_text"
      type="textarea"
      :rows="3"
      :label="__('Update')"
      :placeholder="
        __('One to three short lines: what is done, what is pending')
      "
      class="sm:col-span-2"
    />
    <FormControl
      v-model="draft.next_step"
      type="text"
      :label="__('Next step')"
    />
    <TextInput
      v-model="draft.next_step_date"
      type="date"
      :label="__('Next step date')"
    />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { FormControl, TextInput } from "frappe-ui";
import { computed } from "vue";
import { NOTHING, type StatusDraft } from "../projectStatusMeta";

const props = defineProps<{ stages: string[]; waitingOn: string[] }>();
const draft = defineModel<StatusDraft>({ required: true });

const stageOptions = computed(() => [
  { label: __("Choose a stage"), value: "" },
  ...props.stages.map((value) => ({ label: __(value), value })),
]);
const waitingOptions = computed(() =>
  props.waitingOn.map((value) => ({ label: __(value), value }))
);
</script>
