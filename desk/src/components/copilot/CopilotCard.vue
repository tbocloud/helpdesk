<template>
  <!-- one of Copilot's messages: a title, a few plain lines, facts, a box to write in, at most two
       buttons and its links (the TBO Copilot panel and the ticket's Copilot chat draw it the same) -->
  <div class="rounded-lg border px-3 py-2 text-base" :class="toneClass">
    <div v-if="card.title" class="mb-1 font-medium text-ink-gray-9">
      {{ card.title }}
    </div>
    <p
      v-for="(line, i) in card.lines"
      :key="i"
      class="whitespace-pre-line text-ink-gray-8"
    >
      {{ line }}
    </p>
    <dl
      v-if="card.facts?.length"
      class="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm"
    >
      <template v-for="([k, v], i) in card.facts" :key="i">
        <dt class="text-ink-gray-5">{{ k }}</dt>
        <dd class="text-ink-gray-8">{{ v }}</dd>
      </template>
    </dl>
    <template v-if="card.actions?.length">
      <textarea
        v-for="field in card.inputs || []"
        :key="field.id"
        v-model="values[field.id]"
        :placeholder="field.label"
        :aria-label="field.label"
        rows="2"
        class="mt-2 w-full rounded border-outline-gray-2 bg-surface-white text-sm"
      />
    </template>
    <p v-if="status" class="mt-1.5 text-sm text-ink-gray-5">{{ status }}</p>
    <div
      v-if="card.actions?.length || card.links?.length"
      class="mt-2 flex flex-wrap gap-1.5"
    >
      <Button
        v-for="(a, i) in card.actions"
        :key="i"
        size="sm"
        :variant="a.style === 'positive' ? 'solid' : 'subtle'"
        :theme="a.style === 'destructive' ? 'red' : 'gray'"
        :loading="busy"
        @click="emit('press', a, { ...values })"
      >
        {{ a.label }}
      </Button>
      <a
        v-for="([label, url], i) in card.links"
        :key="'l' + i"
        :href="url"
        target="_blank"
        rel="noopener"
        class="inline-flex items-center rounded px-2 py-1 text-sm text-ink-gray-7 underline underline-offset-2 hover:text-ink-gray-9"
      >
        {{ label }}
      </a>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Button } from "frappe-ui";
import { computed, reactive } from "vue";

export type CopilotAction = {
  label: string;
  verb: string;
  style?: string;
  data: Record<string, unknown>;
};
export type CopilotCardData = {
  title?: string;
  lines?: string[];
  facts?: [string, string][];
  links?: [string, string][];
  actions?: CopilotAction[];
  inputs?: { id: string; label: string }[];
  tone?: string;
};

const props = defineProps<{
  card: CopilotCardData;
  busy?: boolean;
  /** what became of the card's proposal or draft (Done, Sent by …) */
  status?: string | null;
}>();
const emit = defineEmits<{
  press: [action: CopilotAction, inputs: Record<string, string>];
}>();

const values = reactive<Record<string, string>>({});

const toneClass = computed(() => {
  if (props.card.tone === "good") return "border-outline-green-2 bg-surface-green-1";
  if (props.card.tone === "warning")
    return "border-outline-amber-2 bg-surface-amber-1";
  return "border-outline-gray-2 bg-surface-white";
});
</script>
