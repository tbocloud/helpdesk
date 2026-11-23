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

    <!-- at a glance: the proposal in four figures -->
    <ul
      v-if="glance.length"
      class="grid grid-cols-[repeat(auto-fit,minmax(9.5rem,1fr))] gap-3 border-b border-outline-gray-2 px-6 py-5"
      role="list"
      :aria-label="__('At a glance')"
    >
      <li
        v-for="tile in glance"
        :key="tile.label"
        class="min-w-0 rounded-lg border border-outline-gray-2 border-t-4 px-3 py-2.5"
        :style="{
          borderTopColor: DOC_TONES[glance.indexOf(tile) % DOC_TONES.length],
        }"
      >
        <p
          class="text-2xs font-semibold uppercase tracking-wider text-ink-gray-6"
        >
          {{ tile.label }}
        </p>
        <!-- one line: the preview pane is narrow, so tiles reflow by width (four across only when
             each gets 9.5rem) and a value up to "₹1,25,00,000.00" fits at text-base -->
        <p
          class="mt-1 whitespace-nowrap font-mono text-base font-semibold tabular-nums text-ink-gray-9"
        >
          {{ tile.value }}
        </p>
        <p v-if="tile.note" class="text-xs text-ink-gray-6">{{ tile.note }}</p>
      </li>
    </ul>

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
        <p
          v-if="b.cards.length && b.effort"
          class="mb-2 text-p-sm text-ink-gray-6"
        >
          {{
            __(
              "{0} modules · {1} days of effort",
              String(b.cards.length),
              String(b.effort)
            )
          }}
        </p>
        <ul
          v-if="b.cards.length"
          class="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-2"
          role="list"
        >
          <li
            v-for="(card, k) in b.cards"
            :key="k"
            class="rounded-md border border-outline-gray-2 border-t-4 p-3"
            :style="{ borderTopColor: DOC_TONES[card.tone] }"
          >
            <p
              v-if="card.app"
              class="mb-0.5 text-2xs font-semibold uppercase tracking-wider text-brand-ink"
            >
              {{ card.app }}
            </p>
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
            <div v-if="card.days" class="mt-2">
              <p class="text-xs tabular-nums text-ink-gray-6">
                {{ __("{0} days", String(card.days)) }}
              </p>
              <div
                class="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                aria-hidden="true"
              >
                <div
                  class="h-full rounded-full bg-brand"
                  :style="{ width: `${card.bar}%` }"
                />
              </div>
            </div>
          </li>
        </ul>

        <!-- the AMC plans, after the note above them (as on the client's page) -->
        <template v-if="b.plans.length">
          <template v-for="(part, j) in b.parts" :key="`n${j}`">
            <p
              v-if="part.kind === 'text'"
              class="mb-3 whitespace-pre-line text-p-sm text-ink-gray-7"
            >
              {{ part.lines.join("\n") }}
            </p>
          </template>
          <!-- free support after go-live, then the optional AMC -->
          <div
            v-if="freeMonths"
            class="mt-3 grid grid-cols-[48%_1fr] gap-1 text-2xs font-semibold uppercase tracking-wider"
          >
            <span class="text-ink-gray-6">{{ __("Go-live") }}</span>
            <span class="text-brand-ink">{{
              __("Month {0} onwards", String(freeMonths + 1))
            }}</span>
            <span
              class="px-3 py-2 text-white"
              :style="{ background: DOC_TONES[1] }"
              >{{ __("{0} months free support", String(freeMonths)) }}</span
            >
            <span
              class="px-3 py-2 text-white"
              :style="{ background: DOC_TONES[0] }"
              >{{ __("Optional AMC · annual plan") }}</span
            >
          </div>
          <ul
            class="mb-3 mt-4 grid grid-cols-1 items-start gap-4 sm:grid-cols-[repeat(auto-fit,minmax(11rem,1fr))]"
            role="list"
            :aria-label="__('AMC plans')"
          >
            <li
              v-for="(plan, k) in b.plans"
              :key="k"
              class="relative flex flex-col overflow-hidden rounded-xl border bg-surface-base"
              :class="
                plan.recommended
                  ? 'border-brand shadow-md'
                  : 'border-outline-gray-2'
              "
            >
              <!-- the header band: the plan and its yearly fee -->
              <div
                class="px-4 pb-4 pt-3.5"
                :class="
                  plan.recommended
                    ? 'bg-brand text-brand-on'
                    : 'bg-surface-gray-1 text-ink-gray-9'
                "
              >
                <div class="flex items-center justify-between gap-2">
                  <p class="text-base font-semibold">{{ plan.name }}</p>
                  <span
                    v-if="plan.recommended"
                    class="shrink-0 rounded-full border border-current px-2 py-0.5 text-2xs font-semibold uppercase tracking-wide"
                    >{{ __("Recommended") }}</span
                  >
                </div>
                <p
                  v-if="plan.fee"
                  class="mt-2 flex items-baseline gap-1.5 font-mono tabular-nums"
                >
                  <span class="text-2xl font-semibold">{{ plan.fee }}</span>
                  <span
                    class="font-sans text-xs"
                    :class="plan.recommended ? 'opacity-80' : 'text-ink-gray-6'"
                    >{{ __("a year") }}</span
                  >
                </p>
              </div>

              <!-- how much of the support it covers -->
              <div class="px-4 pt-3">
                <div
                  class="flex items-baseline justify-between text-xs text-ink-gray-6"
                >
                  <span>{{ __("Coverage") }}</span>
                  <span class="font-mono tabular-nums text-ink-gray-8">{{
                    __(
                      "{0} of {1}",
                      String(plan.included),
                      String(plan.features.length)
                    )
                  }}</span>
                </div>
                <div
                  class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
                  role="img"
                  :aria-label="
                    __(
                      '{0} of {1} services included',
                      String(plan.included),
                      String(plan.features.length)
                    )
                  "
                >
                  <div
                    class="h-full rounded-full bg-brand"
                    :style="{
                      width: `${
                        plan.features.length
                          ? (plan.included / plan.features.length) * 100
                          : 0
                      }%`,
                    }"
                  />
                </div>
              </div>

              <ul class="flex flex-col gap-2 px-4 pb-4 pt-3 text-p-xs">
                <li
                  v-for="(f, m) in plan.features"
                  :key="m"
                  class="flex gap-2"
                  :class="f.on ? 'text-ink-gray-8' : 'text-ink-gray-5'"
                >
                  <span
                    class="mt-px flex size-4 shrink-0 items-center justify-center rounded-full"
                    :class="
                      f.on
                        ? 'bg-brand-soft text-brand-ink'
                        : 'bg-surface-gray-2'
                    "
                    aria-hidden="true"
                  >
                    <LucideCheck v-if="f.on" class="size-3" />
                    <LucideMinus v-else class="size-3" />
                  </span>
                  <span>
                    <span class="sr-only">{{
                      f.on ? __("Included:") : __("Not included:")
                    }}</span>
                    {{ f.label }}
                    <span v-if="f.detail" class="block text-ink-gray-6">{{
                      f.detail
                    }}</span>
                  </span>
                </li>
              </ul>
            </li>
          </ul>
        </template>

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

        <template v-for="(part, j) in b.plans.length ? [] : b.parts" :key="j">
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
          <!-- big-number tiles -->
          <ul
            v-else-if="part.kind === 'stats'"
            class="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4"
            role="list"
          >
            <li
              v-for="(item, k) in part.items"
              :key="k"
              class="border-t-4 bg-surface-gray-1 px-3 py-3"
              :style="{ borderTopColor: DOC_TONES[item.tone] }"
            >
              <span
                class="block text-3xl font-extrabold leading-none tabular-nums"
                :style="{ color: DOC_TONE_INK[item.tone] }"
                >{{ item.figure }}</span
              >
              <span
                v-if="item.label"
                class="mt-2 block text-xs font-semibold text-ink-gray-9"
                >{{ item.label }}</span
              >
              <span v-if="item.detail" class="block text-xs text-ink-gray-6">{{
                item.detail
              }}</span>
            </li>
          </ul>
          <!-- short subsections, deliverables -->
          <ul
            v-else-if="part.kind === 'cards'"
            class="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-2"
            role="list"
          >
            <li
              v-for="(item, k) in part.items"
              :key="k"
              class="border-t-4 bg-surface-gray-1 px-3 py-3"
              :style="{ borderTopColor: DOC_TONES[item.tone] }"
            >
              <span class="block text-sm font-semibold text-ink-gray-9">{{
                item.title
              }}</span>
              <span
                v-if="item.text"
                class="mt-1 block text-p-xs text-ink-gray-7"
                >{{ item.text }}</span
              >
            </li>
          </ul>
          <ol
            v-else-if="part.kind === 'numbered'"
            class="mb-3 divide-y divide-outline-gray-1 text-p-sm text-ink-gray-7"
          >
            <li
              v-for="item in part.items"
              :key="item.number"
              class="flex gap-3 py-2"
            >
              <span
                class="flex size-6 shrink-0 items-center justify-center rounded-full font-mono text-xs font-bold text-white"
                :style="{ background: DOC_TONES[0] }"
                aria-hidden="true"
                >{{ item.number }}</span
              >
              <span>
                <b v-if="item.text" class="font-semibold text-ink-gray-9"
                  >{{ item.title }}:</b
                >
                {{ item.text || item.title }}
              </span>
            </li>
          </ol>
          <div
            v-else-if="part.kind === 'callout'"
            class="mb-3 border-l-4 px-4 py-3"
            :style="{ borderLeftColor: DOC_TONES[1], background: '#e8f3f0' }"
          >
            <p class="text-sm font-semibold text-ink-gray-9">
              {{ part.title }}
              <span
                v-if="part.tag"
                class="ml-1.5 rounded-full px-2 py-0.5 align-middle text-2xs font-bold uppercase tracking-wider text-white"
                :style="{ background: DOC_TONES[1] }"
                >{{ part.tag }}</span
              >
            </p>
            <p
              v-for="(line, k) in part.lines"
              :key="k"
              class="mt-1 text-p-sm text-ink-gray-7"
            >
              {{ line }}
            </p>
          </div>
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

        <!-- the implementation plan's phases as numbered markers on a line -->
        <ol
          v-if="b.phases.length"
          class="mb-3 mt-2 grid grid-cols-2 gap-x-2 gap-y-4 sm:grid-cols-4"
        >
          <li
            v-for="(phase, k) in b.phases"
            :key="k"
            class="relative text-center"
          >
            <span
              class="absolute inset-x-0 top-[1.125rem] border-t-2 border-outline-gray-3"
              aria-hidden="true"
            />
            <span
              class="relative inline-flex size-9 items-center justify-center rounded font-mono text-base font-bold"
              :style="{
                background: DOC_TONES[phase.tone],
                color: phase.tone === 2 ? '#1c1b19' : '#fff',
              }"
              aria-hidden="true"
              >{{ k + 1 }}</span
            >
            <span class="mt-2 block text-sm font-semibold text-ink-gray-9">{{
              phase.name
            }}</span>
            <span v-if="phase.text" class="block text-xs text-ink-gray-6">{{
              phase.text
            }}</span>
          </li>
        </ol>

        <!-- the payment milestones as columns, the amount in a band -->
        <div v-if="b.steps.length" class="mb-3">
          <ol class="grid grid-cols-1 gap-1.5 sm:flex">
            <li
              v-for="(step, k) in b.steps"
              :key="k"
              class="min-w-0 bg-surface-gray-1"
              :style="{
                flex: `${Math.max(step.width, 60 / b.steps.length)} 1 0%`,
              }"
            >
              <p
                class="px-2 py-3 text-center font-mono text-base font-bold tabular-nums text-white"
                :style="{ background: step.shade }"
              >
                {{ step.amount || step.share }}
              </p>
              <p class="px-3 pb-3 pt-2.5">
                <span
                  class="block font-mono text-2xs font-semibold uppercase tracking-wider text-brand-ink"
                  >{{ step.number }} · {{ step.share }}</span
                >
                <span class="mt-1 block text-sm text-ink-gray-8">{{
                  step.label
                }}</span>
              </p>
            </li>
          </ol>
          <p
            v-if="quotation"
            class="mt-3 border-t-2 border-outline-gray-3 pt-2 text-right font-mono text-xl font-bold tabular-nums text-ink-gray-9"
          >
            <span
              class="mr-2 font-sans text-2xs font-semibold uppercase tracking-wider text-ink-gray-6"
              >{{ __("Total") }}</span
            >{{ money(quotation.grand_total, quotation.currency) }}
          </p>
        </div>

        <template v-if="b.section.section_type === PRICING_SECTION">
          <!-- how the total splits -->
          <div
            v-if="breakdown.length"
            class="mb-4 mt-1"
            role="img"
            :aria-label="
              __('How the total splits') +
              ': ' +
              breakdown.map((p) => `${p.label} ${p.share}`).join(', ')
            "
          >
            <div
              class="flex h-3.5 overflow-hidden rounded-full bg-surface-gray-2"
              aria-hidden="true"
            >
              <span
                v-for="(p, k) in breakdown"
                :key="k"
                class="h-full"
                :class="p.tax ? 'bg-surface-gray-5' : 'bg-brand'"
                :style="{ width: `${p.width}%`, opacity: p.tax ? 1 : p.tone }"
              />
            </div>
            <ul class="mt-2.5 flex flex-col gap-1 text-sm" aria-hidden="true">
              <li
                v-for="(p, k) in breakdown"
                :key="k"
                class="flex items-center gap-2"
              >
                <span
                  class="size-2.5 shrink-0 rounded-sm"
                  :class="p.tax ? 'bg-surface-gray-5' : 'bg-brand'"
                  :style="{ opacity: p.tax ? 1 : p.tone }"
                />
                <span class="min-w-0 flex-1 truncate text-ink-gray-8">{{
                  p.label
                }}</span>
                <span class="font-mono tabular-nums text-ink-gray-8">{{
                  p.amount
                }}</span>
                <span
                  class="w-10 text-right font-mono tabular-nums text-ink-gray-6"
                  >{{ p.share }}</span
                >
              </li>
            </ul>
          </div>
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
import LucideCheck from "~icons/lucide/check";
import LucideMinus from "~icons/lucide/minus";
import LetterHeadPart from "./LetterHeadPart.vue";
import {
  NO_IMAGE,
  PART_STARTS,
  DOC_TONES,
  DOC_TONE_INK,
  PRICING_SECTION,
  SECTION_LABELS,
  drawParts,
  mainAppLabel,
  priceGroups,
  textParts,
  type LetterHeadPreview,
  type ProposalModule,
  type ProposalQuotation,
  type ProposalSection,
  type DrawnPart,
  type SectionType,
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
  /** the AMC plan recommended (its title), marked on its card */
  amcPlan?: string | null;
}>();

type ModuleCard = {
  name: string;
  fit: string;
  about: string;
  features: string[];
  /** its effort, and as a bar against the largest module's */
  days: number;
  bar: number;
  /** the app it belongs to, when the proposal spans more than one */
  app: string;
  tone: number;
};

/** As on the client's page: each card's effort, grouped and labelled by app when there are several. */
function withEffort(cards: ModuleCard[]): ModuleCard[] {
  const days = Object.fromEntries(
    props.modules.map((m) => [m.module_name, Number(m.effort_days) || 0])
  );
  const most = Math.max(0, ...Object.values(days));
  for (const c of cards) {
    c.days = days[c.name] || 0;
    c.tone = cards.indexOf(c) % DOC_TONES.length;
    c.bar = most ? (c.days / most) * 100 : 0;
  }
  const groups = priceGroups(cards.map((c) => c.name));
  if (groups.length < 2) return cards;
  const labels = {
    main: mainAppLabel(props.solutionType),
    mobile: __("Mobile app"),
    website: __("Website"),
  };
  return groups.flatMap((g) =>
    g.names.map((name) => ({
      ...cards.find((c) => c.name === name)!,
      app: labels[g.key],
    }))
  );
}

type Milestone = {
  number: string;
  /** its band's shade, darkest first (TBO Smart's .s0–.s3) */
  shade: string;
  label: string;
  share: string;
  width: number;
  /** its amount, once the proposal is priced */
  amount: string;
};

const PAY_SHADES = ["#1d3f52", "#2c5d72", "#3a748d", "#6595aa"];

/**
 * The free support period after go-live, read from the Warranty & Support text as TBO Smart's
 * free_support_months does, for the AMC's go-live → AMC line.
 */
const freeMonths = computed(() => {
  const text = props.sections
    .filter((s) => s.section_type === "Warranty & Support" && (s.enabled ?? 1))
    .map((s) => s.body || "")
    .join(" ")
    .toLowerCase();
  const words: Record<string, number> = {
    one: 1,
    two: 2,
    three: 3,
    four: 4,
    six: 6,
    nine: 9,
    twelve: 12,
  };
  const months = text.match(
    new RegExp(`\\b(\\d{1,2}|${Object.keys(words).join("|")})[\\s-]*months?\\b`)
  );
  if (months) return Number(months[1]) || words[months[1]];
  const days = Number(text.match(/\b(\d{2,3})[\s-]*days?\b/)?.[1] || 0);
  return days && days % 30 === 0 ? days / 30 : 0;
});

/**
 * The payment terms table ("milestone | share") as columns split by each share, as the client's
 * page draws it; none (the table stays) unless the shares add up to 100%.
 */
function milestones(table: {
  header: string[];
  rows: string[][];
  hidden?: boolean;
}): Milestone[] {
  const q = props.quotation;
  const steps = table.rows.map((r, k) => {
    const share = Number(String(r[1] ?? "").replace("%", "")) || 0;
    return {
      number: String(k + 1).padStart(2, "0"),
      shade: PAY_SHADES[k % PAY_SHADES.length],
      label: r[0],
      share: `${share}%`,
      width: share,
      amount: q ? money((q.grand_total * share) / 100, q.currency) : "",
    };
  });
  const total = steps.reduce((sum, s) => sum + s.width, 0);
  if (
    !steps.length ||
    steps.some((s) => s.width <= 0) ||
    Math.round(total * 100) !== 10000
  )
    return [];
  table.hidden = true;
  return steps;
}

/** The investment's split for the stacked bar: the largest lines (the rest as "Other"), or the project alone when consolidated, then the taxes. */
const SPLIT_SHOWN = 5;
const SPLIT_TONES = [1, 0.8, 0.6, 0.45, 0.3];
const breakdown = computed(() => {
  const q = props.quotation;
  if (!q) return [];
  const taxes = q.total_taxes_and_charges || 0;
  let lines: [string, number][] = q.items
    .map(
      (l) =>
        [
          l.description && l.description !== l.item_name
            ? l.description
            : l.item_name || l.item_code,
          l.amount ?? 0,
        ] as [string, number]
    )
    .filter(([, a]) => a > 0);
  let listed = lines.reduce((sum, [, a]) => sum + a, 0);
  if (props.pricingMode === "Consolidated" || !listed) {
    lines = [[__("Project"), q.net_total]];
    listed = q.net_total;
  }
  const whole = q.net_total + taxes;
  if (whole <= 0 || !listed) return [];
  lines.sort((a, b) => b[1] - a[1]);
  if (lines.length > SPLIT_SHOWN) {
    const rest = lines.slice(SPLIT_SHOWN - 1);
    lines = [
      ...lines.slice(0, SPLIT_SHOWN - 1),
      [
        __("Other ({0})", String(rest.length)),
        rest.reduce((s, [, a]) => s + a, 0),
      ],
    ];
  }
  const parts = lines.map(([label, amount], i) => ({
    label,
    value: (amount * q.net_total) / listed,
    tone: SPLIT_TONES[i],
    tax: false,
  }));
  if (taxes)
    parts.push({ label: __("Taxes"), value: taxes, tone: 1, tax: true });
  return parts.map((p) => ({
    ...p,
    amount: money(p.value, q.currency),
    width: (p.value / whole) * 100,
    share: `${Math.round((p.value / whole) * 100)}%`,
  }));
});

/** The proposal in four figures before its first section, as on the client's page. */
const glance = computed(() => {
  if (props.parts === false) return [];
  const timeline = blocks.value.find((b) => b.bars.length);
  const plan = blocks.value.flatMap((b) => b.plans).find((p) => p.recommended);
  const timelineTable = timeline?.parts.find((p) => p.kind === "table") as
    | { header: string[] }
    | undefined;
  const tiles = [
    props.modules.length
      ? {
          label: __("Modules"),
          value: String(props.modules.length),
          note: __("in scope"),
        }
      : null,
    timeline
      ? {
          label: __("Timeline"),
          value: String(
            timeline.bars.reduce((s, b) => s + Number(b.length), 0)
          ),
          note: (timelineTable?.header[1] || __("days")).toLowerCase(),
        }
      : null,
    props.quotation
      ? {
          label: __("Investment"),
          value: money(props.quotation.grand_total, props.quotation.currency),
          note: props.quotation.total_taxes_and_charges
            ? __("with taxes")
            : __("in total"),
        }
      : null,
    plan
      ? { label: __("Support"), value: plan.name, note: __("AMC plan") }
      : props.validTill
      ? {
          label: __("Valid till"),
          value: dayjs(props.validTill).format("D MMM YYYY"),
          note: "",
        }
      : null,
  ].filter((t): t is { label: string; value: string; note: string } => !!t);
  return tiles.length > 1 ? tiles : [];
});

type AmcPlan = {
  name: string;
  fee: string;
  recommended: boolean;
  /** how many of the features it includes */
  included: number;
  features: { label: string; on: boolean; detail: string }[];
};
const INCLUDED = ["yes", "✓", "included"];

/**
 * The AMC table ("what you get | plan…", the yearly fee its last row) as a card a plan, as the
 * ERP site draws it: "–" not included, "Yes" included with no detail.
 */
function amcPlans(table: { header: string[]; rows: string[][] }): AmcPlan[] {
  const rows = table.rows;
  const last = rows[rows.length - 1];
  const fees =
    last && [__("Yearly fee"), "Yearly fee"].includes((last[0] || "").trim())
      ? last
      : null;
  const features = fees ? rows.slice(0, -1) : rows;
  return table.header.slice(1).map((name, i) => {
    const list = features.map((r) => {
      const value = (r[i + 1] || "").trim();
      const on = !["", "–", "-"].includes(value);
      return {
        label: r[0],
        on,
        detail: on && !INCLUDED.includes(value.toLowerCase()) ? value : "",
      };
    });
    return {
      name,
      fee: fees?.[i + 1]?.trim() || "",
      recommended: !!props.amcPlan && name === props.amcPlan,
      included: list.filter((f) => f.on).length,
      features: list,
    };
  });
}

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

type ShownPart = DrawnPart & {
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
      section.section_type === "Image"
        ? []
        : drawParts(textParts(section.body), section.section_type);
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
    let cards: ModuleCard[] = [];
    let bars: { phase: string; length: string; left: number; width: number }[] =
      [];
    if (table && section.section_type === "Modules & Features") {
      table.hidden = true;
      const wide = table.header.length > 3;
      cards = withEffort(
        table.rows.map((r) => ({
          name: r[0],
          fit: r[1] || "",
          about: wide ? r[2] || "" : "",
          features: (r[wide ? 3 : 2] || "")
            .split(";")
            .map((f) => f.trim())
            .filter((f) => f && f !== "–"),
          days: 0,
          bar: 0,
          app: "",
          tone: 0,
        }))
      );
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
    let plans: AmcPlan[] = [];
    if (table && section.section_type === "AMC" && table.header.length > 1)
      plans = amcPlans(table);
    let phases: { name: string; text: string; tone: number }[] = [];
    if (
      table &&
      section.section_type === "Implementation Plan" &&
      table.rows.length
    ) {
      table.hidden = true;
      phases = table.rows.map((r, k) => ({
        name: r[0],
        text: r[1] || "",
        tone: k % DOC_TONES.length,
      }));
    }
    let steps: Milestone[] = [];
    if (table && section.section_type === "Payment Terms")
      steps = milestones(table);
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
      effort: cards.reduce((sum, c) => sum + c.days, 0),
      bars,
      plans,
      steps,
      phases,
    });
  });
  return shown;
});
</script>
