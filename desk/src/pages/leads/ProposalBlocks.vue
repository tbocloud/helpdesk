<template>
  <section class="flex flex-col gap-3" :aria-labelledby="headingId">
    <h2
      :id="headingId"
      class="text-base-medium text-ink-gray-9"
      :class="withGuidance ? 'sr-only' : ''"
    >
      {{ __("Sections") }}
    </h2>
    <p v-if="!sections.length" class="text-p-sm text-ink-gray-6">
      {{ __("No sections yet. Add one below.") }}
    </p>
    <ol class="flex flex-col gap-2" role="list">
      <li
        v-for="(block, i) in sections"
        :key="keys[i]"
        class="rounded-xl border border-outline-gray-2"
        :class="isOn(block) ? 'bg-surface-base' : 'bg-surface-gray-1'"
      >
        <div class="flex flex-wrap items-center gap-2 px-3 py-2">
          <button
            type="button"
            class="flex min-h-[36px] min-w-0 flex-1 items-center gap-2 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            :aria-expanded="isOpen(i)"
            :aria-controls="`${uid}-body-${i}`"
            @click="toggle(i)"
          >
            <LucideChevronRight
              class="size-4 shrink-0 text-ink-gray-5 transition-transform"
              :class="isOpen(i) ? 'rotate-90' : ''"
              aria-hidden="true"
            />
            <span
              class="truncate text-sm font-medium"
              :class="isOn(block) ? 'text-ink-gray-8' : 'text-ink-gray-5'"
              >{{ label(block) }}</span
            >
            <span
              v-if="block.ai"
              class="shrink-0 rounded-full border border-outline-gray-2 px-2 text-xs text-ink-gray-6"
              >{{ __("AI") }}</span
            >
            <span
              v-if="block.edited"
              class="shrink-0 rounded-full border border-outline-gray-2 px-2 text-xs text-ink-gray-6"
              >{{ __("Edited") }}</span
            >
          </button>
          <div class="ml-auto flex items-center gap-1">
            <Switch
              :model-value="isOn(block)"
              :aria-label="__('Show {0} in the proposal', label(block))"
              :disabled="!editable"
              @update:model-value="update(i, { enabled: $event ? 1 : 0 })"
            />
            <template v-if="editable">
              <Button
                v-if="block.rebuildable && !withGuidance"
                variant="ghost"
                :label="
                  block.ai
                    ? __('Regenerate {0}', label(block))
                    : __('Reset {0} to the library', label(block))
                "
                :tooltip="
                  block.ai ? __('Regenerate (AI)') : __('Reset to library')
                "
                :loading="busy === i"
                @click="emit('regenerate', i)"
              >
                <template #icon>
                  <LucideSparkles
                    v-if="block.ai"
                    class="size-4"
                    aria-hidden="true"
                  />
                  <LucideRotateCcw v-else class="size-4" aria-hidden="true" />
                </template>
              </Button>
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
            </template>
          </div>
        </div>
        <div
          v-if="isOpen(i)"
          :id="`${uid}-body-${i}`"
          class="flex flex-col gap-3 border-t border-outline-gray-1 p-4"
        >
          <slot v-if="block.section_type === PRICING_SECTION" name="pricing" />
          <ProposalImageField
            v-if="proposal && !NO_IMAGE.includes(block.section_type)"
            :proposal="proposal"
            :block="block"
            :editable="editable"
            @update="update(i, $event)"
          />
          <FormControl
            v-if="!['Cover', 'Acceptance'].includes(block.section_type)"
            :model-value="block.heading || ''"
            :label="
              block.section_type === 'Image'
                ? __('Heading (optional)')
                : __('Heading')
            "
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
                'What this section should say: the salesperson\'s placeholder and the AI\'s brief.'
              )
            "
            :disabled="!editable"
            @update:model-value="update(i, { guidance: $event })"
          />
          <FormControl
            v-if="!['Image', 'Acceptance'].includes(block.section_type)"
            :model-value="block.body || ''"
            type="textarea"
            :rows="rows(block)"
            :label="bodyLabel(block)"
            :placeholder="guidance[block.section_type] || ''"
            :description="
              editable && !withGuidance
                ? __(
                    'A blank line starts a paragraph; “- ” a list item; “## ” a subheading; “a | b” lines a table; “A → B” a workflow.'
                  )
                : ''
            "
            :disabled="!editable"
            @update:model-value="update(i, { body: $event })"
          />
          <p
            v-if="block.section_type === 'Acceptance'"
            class="text-p-sm text-ink-gray-6"
          >
            {{
              __(
                "Signature boxes for the client and for us. Accepting online fills the client's name, email and date."
              )
            }}
          </p>
        </div>
      </li>
    </ol>
    <div v-if="editable" class="flex flex-wrap items-end gap-2">
      <FormControl
        v-model="newType"
        type="select"
        class="w-60"
        :label="__('Add a section')"
        :options="typeOptions"
      />
      <Button :label="__('Add section')" @click="add">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, FormControl, Switch } from "frappe-ui";
import { computed, nextTick, ref, useId, watch } from "vue";
import LucideArrowDown from "~icons/lucide/arrow-down";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucidePlus from "~icons/lucide/plus";
import LucideRotateCcw from "~icons/lucide/rotate-ccw";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideTrash2 from "~icons/lucide/trash-2";
import ProposalImageField from "./ProposalImageField.vue";
import {
  NO_IMAGE,
  PRICING_SECTION,
  SECTION_LABELS,
  type ProposalSection,
  type SectionType,
  type TemplateSection,
} from "./proposals";

const props = defineProps<{
  sections: TemplateSection[];
  editable: boolean;
  /** each section type's guidance from the template, shown as the placeholder */
  guidance: Record<string, string>;
  sectionTypes: SectionType[];
  /** a template's sections: each also has its guidance */
  withGuidance?: boolean;
  /** the proposal the sections belong to; with it, sections take an image */
  proposal?: string;
  /** the section being regenerated */
  busy?: number | null;
}>();
const emit = defineEmits<{
  (e: "update:sections", value: TemplateSection[]): void;
  (e: "regenerate", index: number): void;
}>();

const uid = `blocks-${useId()}`;
const headingId = `${uid}-heading`;

// stable keys so a moved section keeps its DOM (and focus)
let counter = 0;
const keys = ref<number[]>([]);
/** sections opened or closed by hand, by key; the rest follow `openByDefault` */
const toggled = ref<Record<number, boolean>>({});
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

function isOn(block: ProposalSection) {
  return (block.enabled ?? 1) === 1;
}

/** What people write themselves opens by default; data sections and sections off stay shut. */
function openByDefault(block: TemplateSection) {
  return (
    isOn(block) &&
    (!!props.withGuidance ||
      !!block.ai ||
      ["Custom", "Image", "Cover"].includes(block.section_type))
  );
}

function isOpen(i: number) {
  const key = keys.value[i];
  return key in toggled.value
    ? toggled.value[key]
    : openByDefault(props.sections[i]);
}

function toggle(i: number) {
  toggled.value = { ...toggled.value, [keys.value[i]]: !isOpen(i) };
}

function label(block: ProposalSection) {
  return block.heading || SECTION_LABELS[block.section_type];
}

function rows(block: ProposalSection) {
  if (block.section_type === PRICING_SECTION) return 3;
  return Math.min(16, Math.max(4, (block.body || "").split("\n").length + 1));
}

function bodyLabel(block: ProposalSection) {
  if (props.withGuidance) return __("Default text (optional)");
  if (block.section_type === PRICING_SECTION)
    return __("Notes above the price");
  if (block.section_type === "Cover")
    return __("A line under the title (optional)");
  return __("Text");
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
  // keep the keyboard on the section that moved, on the same arrow if it can go further
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
  const key = counter++;
  keys.value.push(key);
  toggled.value = { ...toggled.value, [key]: true };
  emit("update:sections", [
    ...props.sections,
    {
      section_type: newType.value,
      enabled: 1,
      heading: "",
      body: "",
      ...(props.proposal ? { image: null, image_size: "Full" as const } : {}),
    },
  ]);
}
</script>
