<template>
  <!-- what the client reads at the proposal's link, drawn live from the editor -->
  <article
    class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-label="__('Preview')"
  >
    <LetterHeadPart
      v-if="letterHead?.header"
      :part="letterHead.header"
      class="border-b border-outline-gray-2"
    />
    <div
      class="border-b-4 px-6 py-6"
      :class="graphite ? 'border-outline-gray-5' : 'border-brand'"
    >
      <p
        class="text-sm font-medium"
        :class="graphite ? 'text-ink-gray-7' : 'text-brand-ink'"
      >
        {{ __("Proposal for {0}", client) }}
      </p>
      <h2 class="mt-1 text-2xl font-semibold text-ink-gray-9">
        {{ title || __("Untitled proposal") }}
      </h2>
      <p v-if="validTill" class="mt-2 text-sm tabular-nums text-ink-gray-6">
        {{ __("Valid till {0}", dayjs(validTill).format("D MMMM YYYY")) }}
      </p>
    </div>
    <p v-if="!visible.length" class="px-6 py-8 text-p-sm text-ink-gray-6">
      {{ __("Write a block and it shows here as the client will see it.") }}
    </p>
    <section
      v-for="(block, i) in visible"
      :key="i"
      class="border-b border-outline-gray-1 px-6 py-5 last:border-b-0"
    >
      <h3
        v-if="
          block.section_type !== 'Cover' &&
          (block.section_type !== 'Image' || block.heading)
        "
        class="mb-2 text-lg font-semibold text-ink-gray-9"
      >
        {{ block.heading || SECTION_LABELS[block.section_type] }}
      </h3>
      <figure
        v-if="block.image_url && IMAGE_BLOCKS.includes(block.section_type)"
        class="mb-3"
        :class="block.image_size === 'Half' ? 'sm:max-w-[50%]' : ''"
      >
        <img
          :src="block.image_url"
          :alt="block.image_alt || ''"
          class="block h-auto w-full rounded-lg border border-outline-gray-2"
        />
        <figcaption
          v-if="block.image_caption && block.section_type === 'Image'"
          class="mt-2 text-p-sm text-ink-gray-6"
        >
          {{ block.image_caption }}
        </figcaption>
      </figure>
      <template v-for="(part, j) in textParts(block.body)" :key="j">
        <ul
          v-if="part.kind === 'list'"
          class="mb-3 list-disc pl-5 text-p-sm text-ink-gray-7"
        >
          <li v-for="(item, k) in part.items" :key="k">{{ item }}</li>
        </ul>
        <p
          v-else
          class="mb-3 whitespace-pre-line"
          :class="
            block.section_type === 'Cover'
              ? 'text-p-base text-ink-gray-8'
              : 'text-p-sm text-ink-gray-7'
          "
        >
          {{ part.lines.join("\n") }}
        </p>
      </template>
      <table
        v-if="block.section_type === 'Pricing' && quotation"
        class="mt-2 w-full text-sm"
      >
        <thead>
          <tr
            class="border-b border-outline-gray-2 text-left text-xs text-ink-gray-6"
          >
            <th scope="col" class="py-2 pr-2 font-medium">{{ __("Item") }}</th>
            <th scope="col" class="py-2 text-right font-medium">
              {{ __("Amount") }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(line, k) in quotation.items"
            :key="k"
            class="border-b border-outline-gray-1 align-top"
          >
            <td class="py-2 pr-2 text-ink-gray-8">
              {{ line.item_name || line.item_code }}
              <span
                v-if="line.qty !== 1"
                class="font-mono tabular-nums text-ink-gray-6"
              >
                × {{ line.qty }}</span
              >
              <span
                v-if="line.description && line.description !== line.item_name"
                class="block text-xs text-ink-gray-6"
                >{{ line.description }}</span
              >
            </td>
            <td class="py-2 text-right font-mono tabular-nums text-ink-gray-8">
              {{ money(line.amount ?? 0, quotation.currency) }}
            </td>
          </tr>
        </tbody>
        <tfoot class="text-ink-gray-7">
          <tr v-if="quotation.discount_amount">
            <td class="pt-2">{{ __("Discount") }}</td>
            <td class="pt-2 text-right font-mono tabular-nums">
              − {{ money(quotation.discount_amount, quotation.currency) }}
            </td>
          </tr>
          <tr v-if="quotation.total_taxes_and_charges">
            <td class="pt-1">{{ __("Taxes") }}</td>
            <td class="pt-1 text-right font-mono tabular-nums">
              {{ money(quotation.total_taxes_and_charges, quotation.currency) }}
            </td>
          </tr>
          <tr class="text-base font-semibold text-ink-gray-9">
            <td class="pt-2">{{ __("Total") }}</td>
            <td class="pt-2 text-right font-mono tabular-nums">
              {{ money(quotation.grand_total, quotation.currency) }}
            </td>
          </tr>
        </tfoot>
      </table>
      <p
        v-else-if="block.section_type === 'Pricing'"
        class="text-p-sm text-ink-gray-5"
      >
        {{ __("Price the proposal and its lines show here.") }}
      </p>
    </section>
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
import LetterHeadPart from "./LetterHeadPart.vue";
import {
  IMAGE_BLOCKS,
  SECTION_LABELS,
  textParts,
  type LetterHeadPreview,
  type ProposalQuotation,
  type ProposalSection,
} from "./proposals";

const props = defineProps<{
  title: string;
  client: string;
  theme: string;
  validTill?: string | null;
  sections: ProposalSection[];
  quotation: ProposalQuotation | null;
  letterHead?: LetterHeadPreview | null;
}>();

const graphite = computed(() => props.theme === "Graphite");

/** As on the client's page: an empty block shows nothing, pricing always. */
const visible = computed(() =>
  props.sections.filter(
    (s) =>
      (s.section_type !== "Image" && (s.body || "").trim()) ||
      (s.image_url && IMAGE_BLOCKS.includes(s.section_type)) ||
      s.section_type === "Pricing"
  )
);
</script>
