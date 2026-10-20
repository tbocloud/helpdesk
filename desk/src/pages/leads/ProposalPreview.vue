<template>
  <!-- what the client reads at the proposal's link, drawn live from the editor; the page and
       the PDF on the ERP site are the real thing (Share → Preview link / Download PDF) -->
  <!-- long words (links, emails, codes) wrap rather than push the column wider -->
  <article
    class="min-w-0 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base [overflow-wrap:anywhere]"
    :aria-label="__('Preview')"
  >
    <LetterHeadPart
      v-if="letterHead?.header"
      :part="letterHead.header"
      class="border-b border-outline-gray-2"
    />
    <div class="border-b border-outline-gray-2 px-6 py-8">
      <p class="text-xs font-semibold uppercase tracking-wider text-brand-ink">
        {{ kicker || solutionType || __("Proposal") }}
      </p>
      <h2 class="mt-2 text-2xl font-semibold text-ink-gray-9">
        {{ title || __("Untitled proposal") }}
      </h2>
      <div class="my-4 h-1 w-16 bg-brand" aria-hidden="true" />
      <p class="text-sm text-ink-gray-6">{{ __("Prepared for") }}</p>
      <p class="text-lg text-ink-gray-9">{{ client }}</p>
      <p v-if="validTill" class="mt-3 text-sm tabular-nums text-ink-gray-6">
        {{ __("Valid till {0}", dayjs(validTill).format("D MMMM YYYY")) }}
      </p>
    </div>

    <nav
      v-if="contents !== false && blocks.some((b) => b.number)"
      class="border-b border-outline-gray-2 px-6 py-4"
      :aria-label="__('Contents')"
    >
      <p class="mb-2 text-sm font-medium text-ink-gray-8">
        {{ __("Contents") }}
      </p>
      <ol class="columns-1 gap-6 text-sm text-ink-gray-7 sm:columns-2">
        <li
          v-for="b in blocks.filter((x) => x.number)"
          :key="b.key"
          class="flex break-inside-avoid gap-2"
        >
          <span class="w-6 shrink-0 font-mono tabular-nums text-brand-ink">{{
            b.number
          }}</span
          ><span>{{ b.heading }}</span>
        </li>
      </ol>
    </nav>

    <p v-if="!blocks.length" class="px-6 py-8 text-p-sm text-ink-gray-6">
      {{ __("Write a section and it shows here as the client will see it.") }}
    </p>
    <template v-for="b in blocks" :key="b.key">
      <p
        v-if="b.part"
        class="px-6 pt-6 text-xs font-semibold uppercase tracking-wider text-brand-ink"
      >
        {{ b.part }}
      </p>
      <section class="px-6 py-5">
        <h3
          class="mb-3 border-b-2 border-brand pb-2 text-lg font-semibold text-ink-gray-9"
          :class="b.number ? '' : 'sr-only'"
        >
          <span
            v-if="b.number"
            class="mr-2 font-mono font-medium tabular-nums text-brand-ink"
            >{{ b.number }}</span
          >{{ b.heading }}
        </h3>
        <figure
          v-if="
            b.section.image_url && !NO_IMAGE.includes(b.section.section_type)
          "
          class="mb-3"
          :class="b.section.image_size === 'Half' ? 'sm:max-w-[50%]' : ''"
        >
          <img
            :src="b.section.image_url"
            :alt="b.section.image_alt || ''"
            class="block h-auto w-full rounded-md border border-outline-gray-2"
          />
          <figcaption
            v-if="b.section.image_caption"
            class="mt-2 text-p-sm text-ink-gray-6"
          >
            {{ b.section.image_caption }}
          </figcaption>
        </figure>

        <!-- the module map -->
        <ul
          v-if="b.cards.length"
          class="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-2"
          role="list"
        >
          <li
            v-for="(card, k) in b.cards"
            :key="k"
            class="rounded-md border border-outline-gray-2 border-t-brand border-t-2 p-3"
          >
            <p class="text-sm font-semibold text-ink-gray-9">
              {{ card.name }}
              <span
                v-if="card.fit"
                class="ml-1 rounded-full border border-outline-gray-2 px-1.5 text-xs font-normal text-ink-gray-6"
                >{{ card.fit }}</span
              >
            </p>
            <p v-if="card.about" class="mt-1 text-p-xs text-ink-gray-7">
              {{ card.about }}
            </p>
            <ul
              v-if="card.features.length"
              class="mt-1 list-disc pl-4 text-p-xs text-ink-gray-7"
            >
              <li v-for="(f, j) in card.features" :key="j">{{ f }}</li>
            </ul>
          </li>
        </ul>

        <!-- the timeline bar -->
        <div v-if="b.bars.length" class="mb-3 flex flex-col gap-1.5">
          <div
            v-for="(bar, k) in b.bars"
            :key="k"
            class="grid grid-cols-[8rem_1fr_2.5rem] items-center gap-2 text-xs"
          >
            <span class="truncate text-ink-gray-8">{{ bar.phase }}</span>
            <span class="relative h-3 rounded-sm bg-surface-gray-2">
              <span
                class="absolute inset-y-0 rounded-sm bg-brand"
                :style="{ left: `${bar.left}%`, width: `${bar.width}%` }"
              />
            </span>
            <span class="text-right font-mono tabular-nums text-ink-gray-7">{{
              bar.length
            }}</span>
          </div>
        </div>

        <template v-for="(part, j) in b.parts" :key="j">
          <h4
            v-if="part.kind === 'heading'"
            class="mb-1 mt-3 text-sm font-semibold text-ink-gray-9"
          >
            <span class="mr-1 font-mono tabular-nums text-brand-ink">{{
              part.number
            }}</span
            >{{ part.text }}
          </h4>
          <ul
            v-else-if="part.kind === 'list'"
            class="mb-3 list-disc pl-5 text-p-sm text-ink-gray-7"
          >
            <li v-for="(item, k) in part.items" :key="k">{{ item }}</li>
          </ul>
          <table
            v-else-if="part.kind === 'table' && !part.hidden"
            class="mb-3 w-full text-xs"
          >
            <thead>
              <tr
                class="border-b border-outline-gray-3 text-left text-ink-gray-6"
              >
                <th
                  v-for="(cell, k) in part.header"
                  :key="k"
                  scope="col"
                  class="py-1.5 pr-2 font-medium"
                  :class="part.amounts && k > 0 ? 'text-right' : ''"
                >
                  {{ cell }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(row, k) in part.rows"
                :key="k"
                class="border-b border-outline-gray-1 align-top"
              >
                <td
                  v-for="(cell, c) in row"
                  :key="c"
                  class="py-1.5 pr-2"
                  :class="[
                    c === 0 ? 'font-medium text-ink-gray-8' : 'text-ink-gray-7',
                    part.amounts && c > 0
                      ? 'text-right font-mono tabular-nums'
                      : '',
                  ]"
                >
                  {{ cell }}
                </td>
              </tr>
            </tbody>
          </table>
          <div
            v-else-if="part.kind === 'chain'"
            class="mb-3 flex flex-wrap items-center gap-1 text-xs"
            role="list"
          >
            <template v-for="(step, k) in part.steps" :key="k">
              <span
                role="listitem"
                class="rounded border border-outline-gray-3 px-2 py-1 text-ink-gray-8"
                >{{ step }}</span
              >
              <LucideArrowRight
                v-if="k < part.steps.length - 1"
                class="size-3 text-brand-ink"
                aria-hidden="true"
              />
            </template>
          </div>
          <p
            v-else-if="part.kind === 'text'"
            class="mb-3 whitespace-pre-line text-p-sm text-ink-gray-7"
          >
            {{ part.lines.join("\n") }}
          </p>
        </template>

        <template v-if="b.section.section_type === PRICING_SECTION">
          <table v-if="quotation" class="mt-2 w-full text-sm">
            <thead>
              <tr
                class="border-b border-outline-gray-2 text-left text-xs text-ink-gray-6"
              >
                <th scope="col" class="py-2 pr-2 font-medium">
                  {{
                    pricingMode === "Consolidated" ? __("Project") : __("Item")
                  }}
                </th>
                <th scope="col" class="py-2 text-right font-medium">
                  {{ __("Amount") }}
                </th>
              </tr>
            </thead>
            <tbody v-if="pricingMode === 'Consolidated'">
              <tr class="border-b border-outline-gray-1 align-top">
                <td class="py-2 pr-2 text-ink-gray-8">
                  {{ title }}
                  <span class="block text-xs text-ink-gray-6">{{
                    __(
                      "Includes: {0}",
                      modules.map((m) => m.module_name).join(", ")
                    )
                  }}</span>
                </td>
                <td
                  class="py-2 text-right font-mono tabular-nums text-ink-gray-8"
                >
                  {{ money(quotation.net_total, quotation.currency) }}
                </td>
              </tr>
            </tbody>
            <tbody v-else>
              <tr
                v-for="(line, k) in quotation.items"
                :key="k"
                class="border-b border-outline-gray-1 align-top"
              >
                <td class="py-2 pr-2 text-ink-gray-8">
                  {{
                    line.description && line.description !== line.item_name
                      ? line.description
                      : line.item_name || line.item_code
                  }}
                  <span
                    v-if="line.qty !== 1"
                    class="font-mono tabular-nums text-ink-gray-6"
                  >
                    × {{ line.qty }}</span
                  >
                </td>
                <td
                  class="py-2 text-right font-mono tabular-nums text-ink-gray-8"
                >
                  {{ money(line.amount ?? 0, quotation.currency) }}
                </td>
              </tr>
            </tbody>
            <tfoot class="text-ink-gray-7">
              <tr
                v-if="
                  quotation.discount_amount && pricingMode !== 'Consolidated'
                "
              >
                <td class="pt-2">{{ __("Discount") }}</td>
                <td class="pt-2 text-right font-mono tabular-nums">
                  − {{ money(quotation.discount_amount, quotation.currency) }}
                </td>
              </tr>
              <template
                v-if="
                  quotation.taxes?.length || quotation.total_taxes_and_charges
                "
              >
                <tr>
                  <td class="pt-1">{{ __("Net total") }}</td>
                  <td class="pt-1 text-right font-mono tabular-nums">
                    {{ money(quotation.net_total, quotation.currency) }}
                  </td>
                </tr>
                <!-- each tax line as the client's page shows it ("GST 18%") -->
                <tr v-for="(tax, k) in taxLines" :key="`tax-${k}`">
                  <td class="pt-1">{{ tax.label }}</td>
                  <td class="pt-1 text-right font-mono tabular-nums">
                    {{ money(tax.amount, quotation.currency) }}
                  </td>
                </tr>
              </template>
              <tr class="text-base font-semibold text-ink-gray-9">
                <td class="pt-2">{{ __("Grand total") }}</td>
                <td class="pt-2 text-right font-mono tabular-nums">
                  {{ money(quotation.grand_total, quotation.currency) }}
                </td>
              </tr>
            </tfoot>
          </table>
          <p v-else class="text-p-sm text-ink-gray-5">
            {{ __("Price the proposal and its lines show here.") }}
          </p>
        </template>

        <div
          v-if="b.section.section_type === 'Acceptance'"
          class="grid grid-cols-1 gap-3 sm:grid-cols-2"
        >
          <div
            v-for="side in [client, __('Us')]"
            :key="side"
            class="rounded-md border border-outline-gray-3 p-3 text-xs text-ink-gray-6"
          >
            <p
              class="mb-2 font-semibold uppercase tracking-wider text-brand-ink"
            >
              {{ __("For {0}", side) }}
            </p>
            <p
              v-for="field in signatureFields"
              :key="field"
              class="mt-3 border-t border-outline-gray-3 pt-1"
            >
              {{ field }}
            </p>
          </div>
        </div>
      </section>
    </template>
    <LetterHeadPart
      v-if="letterHead?.footer"
      :part="letterHead.footer"
      class="border-t border-outline-gray-2"
    />
  </article>
</template>

<script setup lang="ts">
import { money } from "@/components/invoicing/invoices";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import { computed } from "vue";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LetterHeadPart from "./LetterHeadPart.vue";
import {
  NO_IMAGE,
  PART_STARTS,
  PRICING_SECTION,
  SECTION_LABELS,
  textParts,
  type LetterHeadPreview,
  type ProposalModule,
  type ProposalQuotation,
  type ProposalSection,
  type SectionType,
  type TextPart,
} from "./proposals";

const props = defineProps<{
  title: string;
  client: string;
  solutionType?: string | null;
  /** the cover's line above the title for a document after the proposal ("Quotation") */
  kicker?: string | null;
  /** false: no contents (the quotation) */
  contents?: boolean;
  /** false: no part titles (only the proposal has parts) */
  parts?: boolean;
  /** the document type's default headings */
  headings?: Record<string, string>;
  validTill?: string | null;
  sections: ProposalSection[];
  quotation: ProposalQuotation | null;
  pricingMode: "Itemised" | "Consolidated";
  modules: ProposalModule[];
  letterHead?: LetterHeadPreview | null;
}>();

/** The tax lines; an older ERP site sends only the total, shown as one "Taxes" line. */
const taxLines = computed(() => {
  const q = props.quotation;
  if (!q) return [];
  return q.taxes?.length
    ? q.taxes
    : [{ label: __("Taxes"), amount: q.total_taxes_and_charges }];
});

const signatureFields = [
  __("Authorised person"),
  __("Designation"),
  __("Signature"),
  __("Date"),
];

type ShownPart = TextPart & {
  number?: string;
  hidden?: boolean;
  amounts?: boolean;
};

/** Each master section's part, from where the parts start (as on the client's page). */
const ORDER: SectionType[] = Object.keys(SECTION_LABELS) as SectionType[];
function partOf(kind: SectionType): string | undefined {
  let part: string | undefined;
  for (const k of ORDER) {
    part = PART_STARTS[k] ?? part;
    if (k === kind)
      return ["Image", "Custom", "Cover"].includes(kind) ? undefined : part;
  }
  return undefined;
}

/**
 * As on the client's page: sections that are on and not empty (the price and the acceptance
 * always), numbered after the cover, their subheadings n.1, n.2…, each part's title first.
 */
const blocks = computed(() => {
  let number = 0;
  let part: string | undefined;
  const shown = [];
  props.sections.forEach((section, i) => {
    if (!(section.enabled ?? 1) || section.section_type === "Cover") return;
    const parts: ShownPart[] =
      section.section_type === "Image" ? [] : textParts(section.body);
    const always = [PRICING_SECTION, "Acceptance"].includes(
      section.section_type
    );
    if (!parts.length && !section.image_url && !always) return;
    const newPart =
      props.parts === false ? undefined : partOf(section.section_type) ?? part;
    const partTitle = newPart && newPart !== part ? newPart : null;
    part = newPart;
    const titled = section.section_type !== "Image" || !!section.heading;
    const n = titled ? ++number : null;
    let sub = 0;
    for (const p of parts) if (p.kind === "heading") p.number = `${n}.${++sub}`;
    const table = parts.find((p) => p.kind === "table") as
      | (ShownPart & { kind: "table" })
      | undefined;
    let cards: {
      name: string;
      fit: string;
      about: string;
      features: string[];
    }[] = [];
    let bars: { phase: string; length: string; left: number; width: number }[] =
      [];
    if (table && section.section_type === "Modules & Features") {
      table.hidden = true;
      const wide = table.header.length > 3;
      cards = table.rows.map((r) => ({
        name: r[0],
        fit: r[1] || "",
        about: wide ? r[2] || "" : "",
        features: (r[wide ? 3 : 2] || "")
          .split(";")
          .map((f) => f.trim())
          .filter((f) => f && f !== "–"),
      }));
    }
    if (table && section.section_type === "Project Timeline") {
      const rows = table.rows
        .map((r) => [r[0], Number(r[1]) || 0] as const)
        .filter(([, d]) => d > 0);
      const total = rows.reduce((sum, [, d]) => sum + d, 0);
      if (total) {
        // a dated timeline (the agreement's) keeps its table under the bars
        table.hidden = table.header.length <= 2;
        let start = 0;
        bars = rows.map(([phase, d]) => {
          const bar = {
            phase,
            length: String(d),
            left: (start / total) * 100,
            width: (d / total) * 100,
          };
          start += d;
          return bar;
        });
      }
    }
    if (table && section.section_type === "Payment Terms" && props.quotation) {
      const q = props.quotation;
      table.amounts = true;
      table.header = [...table.header.slice(0, 2), __("Amount")];
      table.rows = table.rows.map((r) => [
        r[0],
        r[1],
        money(
          (q.grand_total * (Number(String(r[1]).replace("%", "")) || 0)) / 100,
          q.currency
        ),
      ]);
    }
    shown.push({
      key: i,
      section,
      number: n,
      part: partTitle,
      heading:
        section.heading ||
        props.headings?.[section.section_type] ||
        SECTION_LABELS[section.section_type],
      parts,
      cards,
      bars,
    });
  });
  return shown;
});
</script>
