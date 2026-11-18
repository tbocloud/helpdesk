<template>
  <!-- the price before the proposal exists: each module's price by app, the customisations and
       the total; the quotation made on Generate has the final figures (docs/proposals.md) -->
  <div class="flex flex-col gap-4">
    <section
      v-for="g in groups"
      :key="g.key"
      class="flex flex-col gap-2"
      :aria-label="g.label"
    >
      <div class="flex items-baseline justify-between gap-3">
        <h3 class="text-sm font-medium text-ink-gray-8">{{ g.label }}</h3>
        <span class="font-mono text-sm tabular-nums text-ink-gray-8">
          {{ fmt(g.subtotal) }}
        </span>
      </div>
      <ul class="flex flex-col divide-y divide-outline-gray-1" role="list">
        <li
          v-for="r in g.rows"
          :key="r.name"
          class="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5"
        >
          <span class="min-w-0 flex-1 truncate text-sm text-ink-gray-8">
            {{ r.name }}
          </span>
          <button
            v-if="r.set"
            type="button"
            class="rounded text-xs text-ink-gray-6 underline decoration-outline-gray-4 underline-offset-2 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            @click="unset(r.name)"
          >
            {{ __("Use the list price") }}
          </button>
          <span v-else class="text-xs text-ink-gray-5">
            {{ __("List price") }}
          </span>
          <FormControl
            class="w-36"
            :model-value="r.price"
            type="number"
            min="0"
            step="any"
            :aria-label="__('Price of {0}', r.name)"
            @update:model-value="setPrice(r.name, $event)"
          />
        </li>
      </ul>
    </section>

    <section
      v-if="customisations.length"
      class="flex flex-col gap-2"
      :aria-label="__('ERPNext customisation')"
    >
      <div class="flex items-baseline justify-between gap-3">
        <h3 class="text-sm font-medium text-ink-gray-8">
          {{ __("ERPNext customisation") }}
        </h3>
        <span class="font-mono text-sm tabular-nums text-ink-gray-8">
          {{ fmt(customisationTotal) }}
        </span>
      </div>
      <ul class="flex flex-col divide-y divide-outline-gray-1" role="list">
        <li
          v-for="(c, i) in customisations"
          :key="i"
          class="flex items-center justify-between gap-3 py-1.5 text-sm"
        >
          <span class="min-w-0 truncate text-ink-gray-8">{{ c.item }}</span>
          <span
            class="shrink-0 tabular-nums"
            :class="c.price ? 'font-mono text-ink-gray-8' : 'text-ink-gray-6'"
          >
            {{
              c.price
                ? fmt(c.price)
                : __("{0} days at the day rate", String(c.days || 0))
            }}
          </span>
        </li>
      </ul>
      <p class="text-p-xs text-ink-gray-6">
        {{ __("Set each price in Customisations above.") }}
      </p>
    </section>

    <section
      v-if="scoping.branches"
      class="flex flex-col gap-2"
      :aria-label="__('Branch rollout')"
    >
      <div class="flex items-baseline justify-between gap-3">
        <h3 class="text-sm font-medium text-ink-gray-8">
          {{ __("Branch rollout") }}
        </h3>
        <span class="font-mono text-sm tabular-nums text-ink-gray-8">
          {{ perBranch ? fmt(branchTotal) : "–" }}
        </span>
      </div>
      <p class="text-sm tabular-nums text-ink-gray-7">
        {{
          perBranch
            ? __(
                "{0} additional branches × {1}",
                String(scoping.branches),
                fmt(perBranch)
              )
            : __(
                "{0} additional branches: set a price per branch above, or the branch rate on the ERP site.",
                String(scoping.branches)
              )
        }}
      </p>
    </section>

    <div
      class="flex items-baseline justify-between gap-3 border-t border-outline-gray-2 pt-3"
    >
      <span class="text-base font-semibold text-ink-gray-9">
        {{ __("Total before GST") }}
      </span>
      <span
        class="font-mono text-base font-semibold tabular-nums text-ink-gray-9"
      >
        {{ fmt(total) }}
      </span>
    </div>
    <p class="text-p-sm text-ink-gray-6">
      {{ footnote }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { money } from "@/components/invoicing/invoices";
import { __ } from "@/translation";
import { FormControl } from "frappe-ui";
import { computed } from "vue";
import {
  MOBILE_MODULE,
  WEBSITE_MODULE,
  type CatalogueModule,
  type Scoping,
} from "./proposals";

const props = defineProps<{
  scoping: Scoping;
  catalogue: CatalogueModule[];
  /** prices typed here, by module name; a module not in it takes its list price */
  prices: Record<string, number>;
  /** what the modules other than the mobile app and the website are grouped as */
  mainLabel: string;
  currency: string;
  /** the ERP site's branch rate, for branches without a price of their own */
  branchRate?: number | null;
}>();
const emit = defineEmits<{
  (e: "update:prices", value: Record<string, number>): void;
}>();

const fmt = (amount: number) => money(amount, props.currency, true);

function row(name: string) {
  const list =
    props.catalogue.find((m) => m.module_name === name)?.default_price || 0;
  const set = name in props.prices;
  return { name, price: set ? props.prices[name] : list, set };
}

const groups = computed(() => {
  const mods = props.scoping.modules;
  return [
    {
      key: "main",
      label: props.mainLabel,
      names: mods.filter((m) => m !== MOBILE_MODULE && m !== WEBSITE_MODULE),
    },
    {
      key: "mobile",
      label: __("Mobile app"),
      names: mods.filter((m) => m === MOBILE_MODULE),
    },
    {
      key: "website",
      label: __("Website"),
      names: mods.filter((m) => m === WEBSITE_MODULE),
    },
  ]
    .filter((g) => g.names.length)
    .map((g) => {
      const rows = g.names.map(row);
      return {
        ...g,
        rows,
        subtotal: rows.reduce((sum, r) => sum + r.price, 0),
      };
    });
});

const customisations = computed(() =>
  props.scoping.customisations.filter((c) => c.item.trim())
);
const customisationTotal = computed(() =>
  customisations.value.reduce((sum, c) => sum + (c.price || 0), 0)
);
const dayRateDays = computed(() =>
  customisations.value
    .filter((c) => !c.price)
    .reduce((sum, c) => sum + (Number(c.days) || 0), 0)
);
const perBranch = computed(
  () => props.scoping.branch_rate || props.branchRate || 0
);
const branchTotal = computed(
  () => (props.scoping.branches || 0) * perBranch.value
);
const total = computed(
  () =>
    groups.value.reduce((sum, g) => sum + g.subtotal, 0) +
    customisationTotal.value +
    branchTotal.value
);

const footnote = computed(() =>
  [
    dayRateDays.value
      ? __(
          "Plus {0} customisation days at the ERP site's day rate.",
          String(dayRateDays.value)
        )
      : "",
    __(
      "List prices are the module catalogue's; a module linked to an Item takes the client segment's rate. The proposal's quotation, made when you generate it, has the final figures with GST."
    ),
  ]
    .filter(Boolean)
    .join(" ")
);

function setPrice(name: string, value: string | number) {
  const amount = Math.max(Number(value) || 0, 0);
  emit("update:prices", { ...props.prices, [name]: amount });
}

function unset(name: string) {
  const { [name]: _gone, ...rest } = props.prices;
  emit("update:prices", rest);
}
</script>
