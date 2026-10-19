<template>
  <!-- the scoping form: which modules and what else the proposal covers (docs/proposals.md) -->
  <div class="flex flex-col gap-5">
    <fieldset v-if="asks('modules')" class="flex flex-col gap-2">
      <legend class="mb-1 text-sm font-medium text-ink-gray-8">
        {{ __("Modules") }}
      </legend>
      <p class="text-p-sm text-ink-gray-6">
        {{
          __(
            "Each module brings its own pre-written text, scope, deliverables, effort and price."
          )
        }}
      </p>
      <div class="flex flex-wrap gap-2" role="group">
        <button
          v-for="m in moduleChoices"
          :key="m"
          type="button"
          :aria-pressed="model.modules.includes(m)"
          :disabled="disabled"
          class="inline-flex min-h-[36px] items-center gap-1.5 rounded-full border px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight disabled:opacity-60"
          :class="
            model.modules.includes(m)
              ? 'border-transparent bg-brand text-brand-on'
              : 'border-outline-gray-2 bg-surface-base text-ink-gray-8 hover:bg-surface-gray-1'
          "
          @click="toggleModule(m)"
        >
          <LucideCheck
            v-if="model.modules.includes(m)"
            class="size-3.5"
            aria-hidden="true"
          />
          {{ m }}
        </button>
      </div>
      <p v-if="!moduleChoices.length" class="text-p-sm text-ink-gray-6">
        {{ __("No catalogue modules suit this template yet.") }}
      </p>
    </fieldset>

    <fieldset v-if="asks('customisation')" class="flex flex-col gap-2">
      <legend class="mb-1 text-sm font-medium text-ink-gray-8">
        {{ __("Customisations") }}
      </legend>
      <p class="text-p-sm text-ink-gray-6">
        {{
          __(
            "One short line each, in the client's words. The AI turns each into a proper description; the effort stays yours."
          )
        }}
      </p>
      <ul
        v-if="model.customisations.length"
        class="flex flex-col gap-2"
        role="list"
      >
        <li
          v-for="(c, i) in model.customisations"
          :key="i"
          class="grid grid-cols-[1fr_6rem_auto] items-end gap-2"
        >
          <FormControl
            :model-value="c.item"
            :label="i === 0 ? __('What') : ''"
            :aria-label="__('Customisation {0}', String(i + 1))"
            :placeholder="__('e.g. Salary slip in our format')"
            maxlength="140"
            :disabled="disabled"
            @update:model-value="setCustomisation(i, { item: $event })"
          />
          <FormControl
            :model-value="c.days"
            type="number"
            min="0"
            step="0.5"
            :label="i === 0 ? __('Days') : ''"
            :aria-label="
              __('Effort of customisation {0} in days', String(i + 1))
            "
            :disabled="disabled"
            @update:model-value="
              setCustomisation(i, { days: Number($event) || 0 })
            "
          />
          <Button
            variant="ghost"
            :label="__('Remove customisation {0}', String(i + 1))"
            :disabled="disabled"
            @click="removeCustomisation(i)"
          >
            <template #icon>
              <LucideX class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <p v-if="c.detail" class="col-span-3 -mt-1 text-p-xs text-ink-gray-6">
            {{ c.detail }}
          </p>
        </li>
      </ul>
      <div>
        <Button
          :label="__('Add a customisation')"
          :disabled="disabled"
          @click="addCustomisation"
        >
          <template #prefix>
            <LucidePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
    </fieldset>

    <fieldset class="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
      <legend class="mb-2 text-sm font-medium text-ink-gray-8">
        {{ __("The project") }}
      </legend>
      <FormControl
        v-for="key in switches"
        :key="key"
        :model-value="model[key]"
        type="checkbox"
        :label="QUESTION_LABELS[key]"
        :disabled="disabled"
        @update:model-value="set(key, !!$event)"
      />
      <FormControl
        v-if="asks('integrations')"
        class="sm:col-span-2"
        :model-value="model.integrations"
        :label="__('Integrations')"
        :placeholder="__('Systems to connect, e.g. Tally, a payment gateway')"
        maxlength="500"
        :disabled="disabled"
        @update:model-value="set('integrations', $event)"
      />
      <FormControl
        v-if="asks('users')"
        :model-value="model.users || ''"
        type="number"
        min="0"
        :label="__('Number of users')"
        :disabled="disabled"
        @update:model-value="set('users', Number($event) || 0)"
      />
      <FormControl
        v-if="asks('timeline_weeks')"
        :model-value="model.timeline_weeks || ''"
        type="number"
        min="0"
        :label="__('Target timeline (weeks)')"
        :disabled="disabled"
        @update:model-value="set('timeline_weeks', Number($event) || 0)"
      />
      <FormControl
        v-if="asks('hosting')"
        :model-value="model.hosting || ''"
        type="select"
        :label="__('Hosting')"
        :options="hostingOptions"
        :disabled="disabled"
        @update:model-value="set('hosting', $event || null)"
      />
      <div v-if="asks('architecture')" class="flex flex-col gap-1.5">
        <span :id="architectureId" class="text-xs text-ink-gray-5">{{
          __("Architecture section")
        }}</span>
        <TabButtons
          :model-value="model.architecture"
          :aria-labelledby="architectureId"
          :options="architectureOptions"
          @update:model-value="!disabled && set('architecture', $event)"
        />
      </div>
    </fieldset>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, FormControl, TabButtons } from "frappe-ui";
import { computed, useId } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucidePlus from "~icons/lucide/plus";
import LucideX from "~icons/lucide/x";
import {
  QUESTION_LABELS,
  suits,
  type CatalogueModule,
  type Customisation,
  type Question,
  type Scoping,
} from "./proposals";

const props = defineProps<{
  modelValue: Scoping;
  /** the template's questions; empty: all of them */
  questions?: string[];
  catalogue: CatalogueModule[];
  solutionType?: string | null;
  hosting: string[];
  disabled?: boolean;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", value: Scoping): void;
}>();

const architectureId = `scoping-architecture-${useId()}`;
const model = computed(() => props.modelValue);

function asks(key: Question) {
  return !props.questions?.length || props.questions.includes(key);
}

const switches = computed(() =>
  (
    ["mobile_app", "web_app", "data_migration", "amc", "source_code"] as const
  ).filter((key) => asks(key))
);

/** The modules that suit the solution type, and any already ticked. */
const moduleChoices = computed(() => {
  const names = props.catalogue
    .filter((m) => suits(m.solution_types, props.solutionType))
    .map((m) => m.module_name);
  for (const m of props.modelValue.modules)
    if (!names.includes(m)) names.push(m);
  return names;
});

const hostingOptions = computed(() => [
  { label: __("Not decided"), value: "" },
  ...props.hosting.map((h) => ({ label: __(h), value: h })),
]);
const architectureOptions = [
  { label: __("Simple"), value: "Simple" },
  { label: __("Detailed"), value: "Detailed" },
];

function set<K extends keyof Scoping>(key: K, value: Scoping[K]) {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}

function toggleModule(name: string) {
  const modules = props.modelValue.modules.includes(name)
    ? props.modelValue.modules.filter((m) => m !== name)
    : [...props.modelValue.modules, name];
  set("modules", modules);
}

function setCustomisations(list: Customisation[]) {
  emit("update:modelValue", {
    ...props.modelValue,
    customisations: list,
    customisation: list.length > 0,
  });
}

function setCustomisation(i: number, patch: Partial<Customisation>) {
  setCustomisations(
    props.modelValue.customisations.map((c, j) =>
      j === i ? { ...c, ...patch } : c
    )
  );
}

function addCustomisation() {
  setCustomisations([
    ...props.modelValue.customisations,
    { item: "", days: 1 },
  ]);
}

function removeCustomisation(i: number) {
  setCustomisations(props.modelValue.customisations.filter((_, j) => j !== i));
}
</script>
