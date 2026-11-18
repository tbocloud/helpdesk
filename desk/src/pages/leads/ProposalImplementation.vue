<template>
  <!-- what is being implemented: ERP (ERPNext and its add-ons) or Digital Marketing
       (docs/proposals.md "Implementation type") -->
  <div class="flex flex-col gap-3">
    <div class="flex flex-col gap-1.5">
      <span :id="typeId" class="text-sm font-medium text-ink-gray-8">
        {{ __("Implementation type") }}
      </span>
      <TabButtons
        class="self-start"
        :model-value="kind"
        :aria-labelledby="typeId"
        :options="kindOptions"
        @update:model-value="pickKind"
      />
      <p v-if="!kind" class="text-p-sm text-ink-gray-6">
        {{
          __(
            "This template is neither ERP nor Digital Marketing. Pick one to switch to it."
          )
        }}
      </p>
    </div>

    <fieldset v-if="kind === 'ERP'" class="flex flex-col gap-2">
      <legend class="mb-1 text-sm font-medium text-ink-gray-8">
        {{ __("ERPNext, with") }}
      </legend>
      <div class="flex flex-wrap gap-2" role="group">
        <button
          v-for="a in ERP_ADDONS"
          :key="a.value"
          type="button"
          :aria-pressed="addons.includes(a.value)"
          class="inline-flex min-h-[36px] items-center gap-1.5 rounded-full border px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          :class="
            addons.includes(a.value)
              ? 'border-transparent bg-brand text-brand-on'
              : 'border-outline-gray-2 bg-surface-base text-ink-gray-8 hover:bg-surface-gray-1'
          "
          @click="toggle(a.value)"
        >
          <LucideCheck
            v-if="addons.includes(a.value)"
            class="size-3.5"
            aria-hidden="true"
          />
          {{ a.label }}
        </button>
      </div>
      <p class="text-p-sm text-ink-gray-6">
        {{
          __("Pick any mix. Leave the mobile app off for ERPNext without one.")
        }}
      </p>
    </fieldset>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { TabButtons } from "frappe-ui";
import { computed, useId } from "vue";
import LucideCheck from "~icons/lucide/check";
import {
  ERP_ADDONS,
  erpAddons,
  IMPLEMENTATION_LABELS,
  implementationOf,
  implementations,
  withAddon,
  withImplementation,
  type ErpAddon,
  type Implementation,
  type ImplementationChoice,
  type ProposalTemplate,
  type Scoping,
} from "./proposals";

const props = defineProps<{
  template: string;
  scoping: Scoping;
  /** the enabled templates */
  templates: ProposalTemplate[];
}>();
const emit = defineEmits<{
  (e: "change", value: ImplementationChoice): void;
}>();

const typeId = `proposal-implementation-${useId()}`;

const kindOptions = computed(() =>
  implementations(props.templates).map((k) => ({
    label: IMPLEMENTATION_LABELS[k],
    value: k,
  }))
);
const kind = computed(() =>
  implementationOf(
    props.templates.find((t) => t.name === props.template)?.solution_type
  )
);

const addons = computed(() => erpAddons(props.scoping));

function pickKind(value: Implementation) {
  if (value === kind.value) return;
  const next = withImplementation(value, props.scoping, props.templates);
  if (next) emit("change", next);
}

function toggle(addon: ErpAddon) {
  emit(
    "change",
    withAddon(
      addon,
      !addons.value.includes(addon),
      { template: props.template, scoping: props.scoping },
      props.templates
    )
  );
}
</script>
