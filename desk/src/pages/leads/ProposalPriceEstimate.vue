<template>
  <!-- the price before the proposal exists: each module's price by app, the customisations and
       the total; the quotation made on Generate has the final figures (docs/proposals.md) -->
  <div class="flex flex-col gap-4">
    <div class="flex flex-col gap-1.5">
      <TabButtons
        class="self-start"
        :model-value="scoping.price_basis"
        :aria-label="__('Price by')"
        :options="basisOptions"
        @update:model-value="patch({ price_basis: $event as PriceBasis })"
      />
      <p class="text-p-xs text-ink-gray-6">{{ basisHint }}</p>
    </div>

    <ul
      v-if="scoping.price_basis === 'Custom'"
      class="flex flex-col"
      role="list"
      :aria-label="__('Custom price')"
    >
      <ProposalPriceRow
        :label="__('All modules')"
        :detail="scoping.modules.join(', ')"
        :price="customPrice"
        :set="scoping.custom_price !== null"
        several
        @price="setCustom"
      />
    </ul>

    <template v-else>
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
          <template v-if="scoping.price_basis === 'App'">
            <ProposalPriceRow
              :label="__('{0} price', g.label)"
              :detail="g.names.join(', ')"
              :price="g.subtotal"
              :set="g.key in scoping.app_prices"
              several
              @price="setApp(g.key, $event)"
            />
          </template>
          <template v-else>
            <ProposalPriceRow
              v-for="r in g.rows"
              :key="r.name"
              :label="r.name"
              :price="r.price"
              :set="r.set"
              @price="setModule(r.name, $event)"
            />
          </template>
        </ul>
      </section>
    </template>

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
import { TabButtons } from "frappe-ui";
import { computed } from "vue";
import ProposalPriceRow from "./ProposalPriceRow.vue";
import {
  listPrice,
  priceGroups,
  type CatalogueModule,
  type PriceBasis,
  type PriceGroup,
  type Scoping,
} from "./proposals";

const props = defineProps<{
  /** its modules, customisations and branches, and the price basis with its prices */
  scoping: Scoping;
  catalogue: CatalogueModule[];
  /** by Module, the prices typed, by module name; a module not in it takes its list price */
  prices: Record<string, number>;
  /** what the modules other than the mobile app and the website are grouped as */
  mainLabel: string;
  currency: string;
  /** the ERP site's branch rate, for branches without a price of their own */
  branchRate?: number | null;
}>();
const emit = defineEmits<{
  (e: "update:scoping", value: Scoping): void;
  (e: "update:prices", value: Record<string, number>): void;
}>();

const fmt = (amount: number) => money(amount, props.currency, true);

const basisOptions = [
  { label: __("Module"), value: "Module" },
  { label: __("App"), value: "App" },
  { label: __("Custom"), value: "Custom" },
];
const basisHint = computed(
  () =>
    ({
      Module: __("A price for each module, a line each on the quotation."),
      App: __("One price for each app, a line each on the quotation."),
      Custom: __("One price for all the modules, one line on the quotation."),
    }[props.scoping.price_basis])
);

const groupLabels = computed<Record<PriceGroup, string>>(() => ({
  main: props.mainLabel,
  mobile: __("Mobile app"),
  website: __("Website"),
}));

function row(name: string) {
  const set = name in props.prices;
  return {
    name,
    price: set ? props.prices[name] : listPrice(props.catalogue, name),
    set,
  };
}

const listTotal = (names: string[]) =>
  names.reduce((sum, n) => sum + listPrice(props.catalogue, n), 0);

const groups = computed(() =>
  priceGroups(props.scoping.modules).map((g) => {
    const rows = g.names.map(row);
    const typed = props.scoping.app_prices[g.key];
    return {
      ...g,
      label: groupLabels.value[g.key],
      rows,
      subtotal:
        props.scoping.price_basis === "Module"
          ? rows.reduce((sum, r) => sum + r.price, 0)
          : typed ?? listTotal(g.names),
    };
  })
);
const customPrice = computed(
  () => props.scoping.custom_price ?? listTotal(props.scoping.modules)
);
const modulesTotal = computed(() =>
  props.scoping.price_basis === "Custom"
    ? customPrice.value
    : groups.value.reduce((sum, g) => sum + g.subtotal, 0)
);

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
  () => modulesTotal.value + customisationTotal.value + branchTotal.value
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
      "List prices are the module catalogue's; a module linked to an Item takes the client segment's rate. The proposal's quotation has the final figures with GST."
    ),
  ]
    .filter(Boolean)
    .join(" ")
);

function patch(next: Partial<Scoping>) {
  emit("update:scoping", { ...props.scoping, ...next });
}

/** null: back to the list price */
function setModule(name: string, price: number | null) {
  const { [name]: _gone, ...rest } = props.prices;
  emit("update:prices", price === null ? rest : { ...rest, [name]: price });
}

function setApp(key: PriceGroup, price: number | null) {
  const { [key]: _gone, ...rest } = props.scoping.app_prices;
  patch({ app_prices: price === null ? rest : { ...rest, [key]: price } });
}

function setCustom(price: number | null) {
  patch({ custom_price: price });
}
</script>
