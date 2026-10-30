<template>
  <!-- The Business overview laid out as 16:9 landscape slides, one section each. Never on
       screen: it is the browser's print (Download as slides). It sits on <body> so the
       app's own layout can't clip or break it, and its page rule is added only while this
       is mounted, so printing any other page is untouched. -->
  <Teleport to="body">
    <component :is="'style'">{{ PRINT_CSS }}</component>
    <div class="business-slides" aria-hidden="true">
      <section class="business-slide title-slide">
        <BrandLogo class="!size-20 rounded-2xl" />
        <p class="bs-eyebrow">{{ config.brandName || "TBO" }}</p>
        <h1 class="bs-title">{{ __("Sales & Business overview") }}</h1>
        <p class="bs-period">{{ range }}</p>
        <p v-if="data.department" class="bs-sub">{{ data.department }}</p>
        <p class="bs-sub">
          {{ __("Generated {0}", dayjs().format("D MMM YYYY, h:mm A")) }}
        </p>
      </section>

      <section class="business-slide">
        <SlideHead :title="__('Headline numbers')" :note="range" />
        <div class="bs-kpis">
          <div v-for="kpi in kpis" :key="kpi.key" class="bs-kpi">
            <span class="bs-kpi-label">{{ kpi.label }}</span>
            <span class="bs-kpi-value">{{ kpi.value }}</span>
            <span class="bs-kpi-sub">{{ kpi.sub }}</span>
          </div>
        </div>
        <ul class="bs-notes">
          <li v-for="note in notes" :key="note">{{ note }}</li>
        </ul>
        <SlideFoot :range="range" :page="1" :pages="pages" />
      </section>

      <section class="business-slide">
        <SlideHead
          :title="__('Pipeline and funnel')"
          :note="__('Open clients now; funnel of the new leads in the period')"
        />
        <div class="bs-cols">
          <div>
            <h3 class="bs-h3">
              {{ __("Pipeline by stage") }}
              <span>{{ __("{0} open", String(data.pipeline.count)) }}</span>
            </h3>
            <BusinessRows :rows="stages" />
          </div>
          <div>
            <h3 class="bs-h3">
              {{ __("Funnel") }}
              <span>{{ __("{0} new leads", String(data.new_leads)) }}</span>
            </h3>
            <BusinessRows :rows="funnel" :max="data.new_leads || 1" />
          </div>
        </div>
        <SlideFoot :range="range" :page="2" :pages="pages" />
      </section>

      <section class="business-slide">
        <SlideHead :title="__('Proposals and onboarding')" :note="range" />
        <div class="bs-kpis bs-kpis-4">
          <div v-for="fact in facts" :key="fact.label" class="bs-kpi">
            <span class="bs-kpi-label">{{ fact.label }}</span>
            <span class="bs-kpi-value">{{ fact.value }}</span>
            <span class="bs-kpi-sub">{{ fact.sub }}</span>
          </div>
        </div>
        <SlideFoot :range="range" :page="3" :pages="pages" />
      </section>

      <section class="business-slide">
        <SlideHead
          :title="__('Revenue by month')"
          :note="__('Invoiced and collected, {0}', range)"
        />
        <div class="bs-chart">
          <BusinessBars
            :labels="revenue.labels"
            :series="revenue.series"
            :format="(v: number) => shortAmount(v, data.currency)"
            :aria-label="__('Revenue invoiced and collected, by month')"
          />
        </div>
        <p class="bs-line">
          <span
            >{{ __("Invoiced") }}
            <b>{{ fullAmount(data.revenue.invoiced, data.currency) }}</b></span
          >
          <span
            >{{ __("Collected") }}
            <b>{{ fullAmount(data.revenue.collected, data.currency) }}</b></span
          >
          <span
            >{{ __("Outstanding now") }}
            <b>{{
              fullAmount(data.revenue.outstanding, data.currency)
            }}</b></span
          >
          <span v-if="data.profit.available"
            >{{ __("Profit") }}
            <b>{{
              fullAmount(data.profit.profit ?? 0, data.currency)
            }}</b></span
          >
        </p>
        <SlideFoot :range="range" :page="4" :pages="pages" />
      </section>

      <section class="business-slide">
        <SlideHead
          :title="__('Last 6 months')"
          :note="__('New leads, wins, invoiced and collected')"
        />
        <div class="bs-cols">
          <BusinessBars
            :labels="trend.labels"
            :series="trend.people"
            :format="(v: number) => String(Math.round(v))"
            :aria-label="__('New leads and clients won, last 6 months')"
          />
          <BusinessBars
            :labels="trend.labels"
            :series="trend.money"
            :format="(v: number) => shortAmount(v, data.currency)"
            :aria-label="__('Revenue invoiced and collected, last 6 months')"
          />
        </div>
        <SlideFoot :range="range" :page="5" :pages="pages" />
      </section>

      <section class="business-slide">
        <SlideHead :title="__('Departments and top clients')" :note="range" />
        <div class="bs-cols">
          <div>
            <h3 class="bs-h3">{{ __("By department") }}</h3>
            <table class="bs-table">
              <thead>
                <tr>
                  <th scope="col">{{ __("Department") }}</th>
                  <th scope="col">{{ __("Open") }}</th>
                  <th scope="col">{{ __("Won") }}</th>
                  <th scope="col">{{ __("Invoiced") }}</th>
                  <th scope="col">{{ __("Collected") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in data.by_department.slice(0, 8)"
                  :key="row.label"
                >
                  <th scope="row">{{ row.label }}</th>
                  <td>{{ row.open }}</td>
                  <td>{{ row.won }}</td>
                  <td>{{ shortAmount(row.invoiced, data.currency) }}</td>
                  <td>{{ shortAmount(row.collected, data.currency) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div>
            <h3 class="bs-h3">{{ __("Top clients by invoiced value") }}</h3>
            <BusinessRows v-if="clients.length" :rows="clients" />
            <p v-else class="bs-sub">
              {{ __("Nothing invoiced in this period.") }}
            </p>
          </div>
        </div>
        <SlideFoot :range="range" :page="6" :pages="pages" />
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import BrandLogo from "@/components/BrandLogo.vue";
import { useConfigStore } from "@/stores/config";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import { computed, defineComponent, h } from "vue";
import type { BusinessOverview } from "../leads";
import BusinessBars from "./BusinessBars.vue";
import {
  businessKpis,
  businessNotes,
  clientRows,
  funnelRows,
  revenueChart,
  stageRows,
  trendCharts,
} from "./businessFigures";
import { fullAmount, rangeText, shortAmount } from "./businessFormat";
import BusinessRows from "./BusinessRows.vue";

const props = defineProps<{ data: BusinessOverview }>();
const config = useConfigStore();

const pages = 6;
const range = computed(() => rangeText(props.data));
const kpis = computed(() => businessKpis(props.data));
const notes = computed(() => businessNotes(props.data));
const stages = computed(() => stageRows(props.data));
const funnel = computed(() => funnelRows(props.data));
const clients = computed(() => clientRows(props.data));
const revenue = computed(() => revenueChart(props.data));
const trend = computed(() => trendCharts(props.data));
const facts = computed(() => {
  const d = props.data;
  const c = d.currency;
  return [
    {
      label: __("Proposals sent"),
      value: String(d.proposals.sent.count),
      sub: fullAmount(d.proposals.sent.value, c),
    },
    {
      label: __("Accepted"),
      value: String(d.proposals.accepted.count),
      sub: fullAmount(d.proposals.accepted.value, c),
    },
    {
      label: __("Acceptance rate"),
      value: `${d.proposals.acceptance_rate}%`,
      sub: __("Accepted of sent, same period"),
    },
    {
      label: __("Declined"),
      value: String(d.proposals.declined),
      sub: "",
    },
    {
      label: __("Clients won"),
      value: String(d.onboarding.won.count),
      sub: fullAmount(d.onboarding.won.value, c),
    },
    {
      label: __("Projects started"),
      value: String(d.onboarding.projects_started),
      sub: __("Linked to a hub project"),
    },
    {
      label: __("Meetings held"),
      value: String(d.meetings_held),
      sub: "",
    },
    {
      label: __("New leads"),
      value: String(d.new_leads),
      sub: "",
    },
  ];
});

const SlideHead = defineComponent({
  props: { title: String, note: String },
  setup: (p) => () =>
    h("header", { class: "bs-head" }, [h("h2", p.title), h("p", p.note)]),
});
const SlideFoot = defineComponent({
  props: { range: String, page: Number, pages: Number },
  setup: (p) => () =>
    h("footer", { class: "bs-foot" }, [
      h("span", `TBO · ${__("Sales & Business overview")} · ${p.range}`),
      h("span", `${p.page! + 1} / ${p.pages! + 1}`),
    ]),
});

// Light colours whatever the app's theme: a printed page is white. The page rule is one
// 16:9 landscape size for every slide.
const PRINT_CSS = `
.business-slides { display: none; }
@media print {
  @page { size: 297mm 167mm; margin: 0; }
  html, body { background: #fff !important; height: auto !important; overflow: visible !important; margin: 0 !important; }
  body > *:not(.business-slides) { display: none !important; }
  .business-slides {
    display: block;
    --biz-ink: #1f2430; --biz-muted: #566070; --biz-line: #d9dee6;
    --biz-track: #e9edf2; --biz-a: #3a748d; --biz-b: #7b8594;
    color: #1f2430; font-family: "Geist", system-ui, sans-serif;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  .business-slide {
    box-sizing: border-box; width: 297mm; height: 167mm; padding: 11mm 14mm 9mm;
    background: #fff; overflow: hidden; break-after: page; page-break-after: always;
    display: flex; flex-direction: column; gap: 6mm; position: relative;
  }
  .business-slide:last-child { break-after: auto; page-break-after: auto; }
  .title-slide { justify-content: center; align-items: flex-start; gap: 4mm; padding-left: 24mm; }
  .bs-eyebrow { margin: 6mm 0 0; font-size: 12pt; letter-spacing: 0.08em; text-transform: uppercase; color: #566070; }
  .bs-title { margin: 0; font-size: 34pt; line-height: 1.1; font-weight: 600; color: #1f2430; }
  .bs-period { margin: 2mm 0 0; font-size: 18pt; color: #3a748d; font-weight: 500; }
  .bs-sub { margin: 0; font-size: 11pt; color: #566070; }
  .bs-head h2 { margin: 0; font-size: 22pt; font-weight: 600; color: #1f2430; }
  .bs-head p { margin: 1mm 0 0; font-size: 11pt; color: #566070; }
  .bs-foot { position: absolute; left: 14mm; right: 14mm; bottom: 6mm; display: flex; justify-content: space-between; font-size: 8.5pt; color: #566070; border-top: 0.3mm solid #d9dee6; padding-top: 2mm; }
  .bs-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5mm; }
  .bs-kpis-4 { grid-template-columns: repeat(4, 1fr); }
  .bs-kpi { display: flex; flex-direction: column; gap: 1mm; border: 0.3mm solid #d9dee6; border-radius: 3mm; padding: 4mm 5mm; }
  .bs-kpi-label { font-size: 11pt; color: #566070; }
  .bs-kpi-value { font-family: "Geist Mono", ui-monospace, monospace; font-variant-numeric: tabular-nums; font-size: 26pt; font-weight: 600; color: #1f2430; line-height: 1.15; }
  .bs-kpi-sub { font-size: 9.5pt; color: #566070; }
  .bs-notes { margin: 0; padding-left: 5mm; font-size: 9.5pt; color: #566070; display: flex; flex-direction: column; gap: 1mm; }
  .bs-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12mm; align-items: start; }
  .bs-h3 { margin: 0 0 3mm; font-size: 13pt; font-weight: 600; color: #1f2430; display: flex; justify-content: space-between; }
  .bs-h3 span { font-size: 10pt; font-weight: 400; color: #566070; }
  .bs-chart { max-width: 235mm; }
  .bs-line { display: flex; gap: 10mm; margin: 0; font-size: 12pt; color: #566070; }
  .bs-line b { font-family: "Geist Mono", ui-monospace, monospace; font-variant-numeric: tabular-nums; color: #1f2430; margin-left: 2mm; }
  .bs-table { width: 100%; border-collapse: collapse; font-size: 10pt; }
  .bs-table th, .bs-table td { padding: 1.6mm 2mm; text-align: right; border-top: 0.3mm solid #d9dee6; font-variant-numeric: tabular-nums; }
  .bs-table thead th { border-top: 0; color: #566070; font-weight: 400; }
  .bs-table th:first-child { text-align: left; font-weight: 400; }
  .bs-table td { font-family: "Geist Mono", ui-monospace, monospace; }
  .business-slides .sr-only { display: none; }
}
`;
</script>
