<template>
  <!-- the proposal's own copy of each module: editing it never changes the catalogue -->
  <section
    class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
    :aria-labelledby="headingId"
  >
    <div class="flex flex-wrap items-center gap-2">
      <h2 :id="headingId" class="text-base-medium text-ink-gray-9">
        {{ __("Modules") }}
      </h2>
      <span class="text-p-sm tabular-nums text-ink-gray-6">
        {{ __("{0} days of effort", String(totalEffort)) }}
      </span>
      <slot name="actions" />
    </div>
    <p v-if="!modules.length" class="text-p-sm text-ink-gray-6">
      {{ __("No modules yet. Add one from the catalogue.") }}
    </p>
    <ul class="flex flex-col gap-2" role="list">
      <li
        v-for="(m, i) in modules"
        :key="m.module_name"
        class="rounded-lg border border-outline-gray-2"
      >
        <div class="flex flex-wrap items-end gap-2 px-3 py-2">
          <div class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-base-medium text-ink-gray-8">{{
              m.module_name
            }}</span>
            <span v-if="m.rate_overridden" class="text-xs text-ink-gray-5">{{
              __("Price set by hand")
            }}</span>
          </div>
          <FormControl
            class="w-32"
            :model-value="m.fit"
            type="select"
            :label="__('Fit')"
            :options="fitOptions"
            :disabled="!editable"
            @update:model-value="update(i, { fit: $event })"
          />
          <FormControl
            class="w-24"
            :model-value="m.effort_days"
            type="number"
            min="0"
            step="0.5"
            :label="__('Days')"
            :disabled="!editable"
            @update:model-value="
              update(i, { effort_days: Number($event) || 0 })
            "
          />
          <FormControl
            class="w-36"
            :model-value="m.rate"
            type="number"
            min="0"
            step="any"
            :label="__('Price')"
            :disabled="!editable"
            @update:model-value="
              update(i, { rate: Number($event) || 0, rate_overridden: 1 })
            "
          />
          <Button
            variant="ghost"
            :label="
              open === i
                ? __('Hide text of {0}', m.module_name)
                : __('Edit text of {0}', m.module_name)
            "
            :aria-expanded="open === i"
            @click="open = open === i ? null : i"
          >
            <template #icon>
              <LucidePencil class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <Button
            v-if="editable"
            variant="ghost"
            :label="__('Remove {0}', m.module_name)"
            @click="remove(i)"
          >
            <template #icon>
              <LucideTrash2 class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
        <div
          v-if="open === i"
          class="flex flex-col gap-3 border-t border-outline-gray-1 px-3 py-3"
        >
          <FormControl
            :model-value="m.description || ''"
            type="textarea"
            :rows="2"
            :label="__('What it covers')"
            :disabled="!editable"
            @update:model-value="update(i, { description: $event })"
          />
          <FormControl
            :model-value="m.features || ''"
            type="textarea"
            :rows="4"
            :label="__('Key features (one a line)')"
            :disabled="!editable"
            @update:model-value="update(i, { features: $event })"
          />
          <div v-if="editable && libraryEntry(m)" class="flex flex-wrap gap-2">
            <Button :label="__('Reset to library')" @click="reset(i)">
              <template #prefix>
                <LucideRotateCcw class="size-4" aria-hidden="true" />
              </template>
            </Button>
            <Button
              v-if="m.rate_overridden"
              :label="__('Use the list price')"
              @click="update(i, { rate_overridden: 0 })"
            />
          </div>
        </div>
      </li>
    </ul>
    <div
      v-if="editable && addable.length"
      class="flex flex-wrap items-end gap-2"
    >
      <FormControl
        v-model="adding"
        type="select"
        class="w-60"
        :label="__('Add a module')"
        :options="addable"
      />
      <Button :label="__('Add module')" :disabled="!adding" @click="add">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
    <p v-if="editable" class="text-p-xs text-ink-gray-6">
      {{
        __(
          "Text changed here is this proposal's only. Sections built from the modules (scope, deliverables, timeline) follow after Save and Regenerate."
        )
      }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, FormControl } from "frappe-ui";
import { computed, ref, useId } from "vue";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlus from "~icons/lucide/plus";
import LucideRotateCcw from "~icons/lucide/rotate-ccw";
import LucideTrash2 from "~icons/lucide/trash-2";
import { suits, type CatalogueModule, type ProposalModule } from "./proposals";

const props = defineProps<{
  modules: ProposalModule[];
  catalogue: CatalogueModule[];
  solutionType?: string | null;
  editable: boolean;
}>();
const emit = defineEmits<{
  (e: "update:modules", value: ProposalModule[]): void;
}>();

const headingId = `proposal-modules-${useId()}`;
const open = ref<number | null>(null);
const adding = ref("");
const fitOptions = ["Standard", "Configured", "Customised"].map((f) => ({
  label: __(f),
  value: f,
}));

const totalEffort = computed(() =>
  props.modules.reduce((sum, m) => sum + (Number(m.effort_days) || 0), 0)
);

const addable = computed(() => [
  { label: __("Pick a module"), value: "" },
  ...props.catalogue
    .filter(
      (c) =>
        suits(c.solution_types, props.solutionType) &&
        !props.modules.some((m) => m.module_name === c.module_name)
    )
    .map((c) => ({ label: c.module_name, value: c.name })),
]);

function libraryEntry(m: ProposalModule) {
  return props.catalogue.find(
    (c) => c.name === m.module || c.module_name === m.module_name
  );
}

function update(i: number, patch: Partial<ProposalModule>) {
  emit(
    "update:modules",
    props.modules.map((m, j) => (j === i ? { ...m, ...patch } : m))
  );
}

function remove(i: number) {
  open.value = null;
  emit(
    "update:modules",
    props.modules.filter((_, j) => j !== i)
  );
}

/** The catalogue's text back in this proposal's copy (its price stays). */
function reset(i: number) {
  const entry = libraryEntry(props.modules[i]);
  if (!entry) return;
  update(i, {
    description: entry.description,
    features: entry.features,
    fit: (entry.fit as ProposalModule["fit"]) || "Configured",
    effort_days: entry.effort_days,
  });
}

/** A catalogue module, priced at its list price by the ERP site on save. */
function add() {
  const entry = props.catalogue.find((c) => c.name === adding.value);
  if (!entry) return;
  emit("update:modules", [
    ...props.modules,
    {
      module: entry.name,
      module_name: entry.module_name,
      fit: (entry.fit as ProposalModule["fit"]) || "Configured",
      description: entry.description,
      features: entry.features,
      effort_days: entry.effort_days,
      rate: entry.default_price,
      rate_overridden: 0,
      item: entry.item,
    },
  ]);
  adding.value = "";
}
</script>
