<template>
  <section class="flex flex-col gap-3" :aria-labelledby="headingId">
    <h2
      :id="headingId"
      class="text-base-medium text-ink-gray-9"
      :class="withGuidance ? 'sr-only' : ''"
    >
      {{ __("Blocks") }}
    </h2>
    <p v-if="!sections.length" class="text-p-sm text-ink-gray-6">
      {{ __("No blocks yet. Add one below.") }}
    </p>
    <ol class="flex flex-col gap-3" role="list">
      <li
        v-for="(block, i) in sections"
        :key="keys[i]"
        class="rounded-xl border border-outline-gray-2 bg-surface-base"
      >
        <div
          class="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 px-4 py-2"
        >
          <span class="font-mono text-xs tabular-nums text-ink-gray-5">{{
            i + 1
          }}</span>
          <span class="text-sm font-medium text-ink-gray-8">{{
            SECTION_LABELS[block.section_type]
          }}</span>
          <div v-if="editable" class="ml-auto flex items-center gap-1">
            <Button
              :id="`${uid}-up-${i}`"
              variant="ghost"
              :label="__('Move {0} up', label(block))"
              :disabled="i === 0"
              @click="move(i, -1)"
            >
              <template #icon>
                <LucideArrowUp class="size-4" aria-hidden="true" />
              </template>
            </Button>
            <Button
              :id="`${uid}-down-${i}`"
              variant="ghost"
              :label="__('Move {0} down', label(block))"
              :disabled="i === sections.length - 1"
              @click="move(i, 1)"
            >
              <template #icon>
                <LucideArrowDown class="size-4" aria-hidden="true" />
              </template>
            </Button>
            <Button
              variant="ghost"
              :label="__('Remove {0}', label(block))"
              @click="remove(i)"
            >
              <template #icon>
                <LucideTrash2 class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
        </div>
        <div class="flex flex-col gap-3 p-4">
          <slot v-if="block.section_type === 'Pricing'" name="pricing" />
          <FormControl
            v-if="block.section_type !== 'Cover'"
            :model-value="block.heading || ''"
            :label="__('Heading')"
            :placeholder="SECTION_LABELS[block.section_type]"
            maxlength="140"
            :disabled="!editable"
            @update:model-value="update(i, { heading: $event })"
          />
          <FormControl
            v-if="withGuidance"
            :model-value="block.guidance || ''"
            type="textarea"
            :rows="2"
            :label="__('Guidance')"
            :description="
              __(
                'What this block should say: the salesperson\'s placeholder and the AI\'s brief.'
              )
            "
            :disabled="!editable"
            @update:model-value="update(i, { guidance: $event })"
          />
          <FormControl
            :model-value="block.body || ''"
            type="textarea"
            :rows="block.section_type === 'Pricing' ? 2 : 5"
            :label="
              withGuidance
                ? __('Default text (optional)')
                : block.section_type === 'Pricing'
                ? __('Words before the price (optional)')
                : __('Text')
            "
            :placeholder="guidance[block.section_type] || ''"
            :description="
              i === 0 && editable
                ? __(
                    'A blank line starts a new paragraph; start a line with “- ” for a list.'
                  )
                : ''
            "
            :disabled="!editable"
            @update:model-value="update(i, { body: $event })"
          />
        </div>
      </li>
    </ol>
    <div v-if="editable" class="flex flex-wrap items-end gap-2">
      <FormControl
        v-model="newType"
        type="select"
        class="w-48"
        :label="__('Add a block')"
        :options="typeOptions"
      />
      <Button :label="__('Add block')" @click="add">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, FormControl } from "frappe-ui";
import { computed, nextTick, ref, useId, watch } from "vue";
import LucideArrowDown from "~icons/lucide/arrow-down";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
import {
  SECTION_LABELS,
  type ProposalSection,
  type SectionType,
  type TemplateSection,
} from "./proposals";

const props = defineProps<{
  sections: TemplateSection[];
  editable: boolean;
  /** each block type's guidance from the template, shown as the placeholder */
  guidance: Record<string, string>;
  sectionTypes: SectionType[];
  /** a template's blocks: each also has its guidance */
  withGuidance?: boolean;
}>();
const emit = defineEmits<{
  (e: "update:sections", value: TemplateSection[]): void;
}>();

const uid = `blocks-${useId()}`;
const headingId = `${uid}-heading`;

// stable keys so a moved block keeps its DOM (and focus)
let counter = 0;
const keys = ref<number[]>([]);
watch(
  () => props.sections.length,
  (length) => {
    while (keys.value.length < length) keys.value.push(counter++);
    keys.value.length = length;
  },
  { immediate: true }
);

const typeOptions = computed(() =>
  props.sectionTypes.map((t) => ({ label: SECTION_LABELS[t], value: t }))
);
const newType = ref<SectionType>("Custom");

function label(block: ProposalSection) {
  return block.heading || SECTION_LABELS[block.section_type];
}

function update(i: number, patch: Partial<TemplateSection>) {
  emit(
    "update:sections",
    props.sections.map((s, j) => (j === i ? { ...s, ...patch } : s))
  );
}

async function move(i: number, by: -1 | 1) {
  const j = i + by;
  if (j < 0 || j >= props.sections.length) return;
  const next = [...props.sections];
  [next[i], next[j]] = [next[j], next[i]];
  [keys.value[i], keys.value[j]] = [keys.value[j], keys.value[i]];
  emit("update:sections", next);
  await nextTick();
  // keep the keyboard on the block that moved, on the same arrow if it can go further
  const edge = by === -1 ? j === 0 : j === props.sections.length - 1;
  const target = document.getElementById(
    `${uid}-${(by === -1) !== edge ? "up" : "down"}-${j}`
  );
  target?.focus();
}

function remove(i: number) {
  keys.value.splice(i, 1);
  emit(
    "update:sections",
    props.sections.filter((_, j) => j !== i)
  );
}

function add() {
  keys.value.push(counter++);
  emit("update:sections", [
    ...props.sections,
    { section_type: newType.value, heading: "", body: "" },
  ]);
}
</script>
