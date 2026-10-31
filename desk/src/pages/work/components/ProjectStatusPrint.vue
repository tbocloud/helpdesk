<template>
  <!-- The report as the coordinator's PDF: A4 portrait, a numbered table of Project,
       Status and Details. Never on screen: it is the browser's print (Download PDF). It
       sits on <body> so the app's layout can't clip or break it, and its page rule exists
       only while this is mounted, so printing any other page is untouched. -->
  <Teleport to="body">
    <component :is="'style'">{{ PRINT_CSS }}</component>
    <div class="status-print" aria-hidden="true">
      <h1>{{ __("Project Status Report") }}</h1>
      <p class="sp-date">{{ dayjs(date).format("D MMMM YYYY") }}</p>
      <table>
        <thead>
          <tr>
            <th class="sp-no">{{ __("No.") }}</th>
            <th class="sp-project">{{ __("Project") }}</th>
            <th class="sp-status">{{ __("Status") }}</th>
            <th>{{ __("Details") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in rows" :key="row.project">
            <td class="sp-no">{{ index + 1 }}</td>
            <td class="sp-project">
              <strong>{{ row.project_name }}</strong>
              <span v-if="row.customer">{{ row.customer }}</span>
            </td>
            <td class="sp-status">
              <strong>{{ row.stage ? __(row.stage) : __("No update") }}</strong>
              <span v-if="isWaiting(row)">
                {{ __("Waiting on {0}", __(row.waiting_on!)) }}
                <template
                  v-if="
                    row.facts.client_wait_days && row.waiting_on === 'Client'
                  "
                >
                  ({{ __("{0} day(s)", String(row.facts.client_wait_days)) }})
                </template>
              </span>
            </td>
            <td>
              <ul v-if="updateLines(row).length">
                <li v-for="line in updateLines(row)" :key="line">{{ line }}</li>
              </ul>
              <p class="sp-facts">{{ factsLine(row) }}</p>
              <p v-for="flag in row.flags" :key="flag.code" class="sp-flag">
                {{ flag.text }}
              </p>
              <p v-if="row.next_step">
                {{ __("Next") }}: {{ row.next_step }}
                <template v-if="row.next_step_date">
                  ({{ dayjs(row.next_step_date).format("D MMM YYYY") }})
                </template>
              </p>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import {
  factsLine,
  isWaiting,
  updateLines,
  type StatusRow,
} from "../projectStatusMeta";

defineProps<{ rows: StatusRow[]; date: string }>();

// Light colours whatever the app's theme: a printed page is white.
const PRINT_CSS = `
.status-print { display: none; }
@media print {
  @page { size: A4 portrait; margin: 12mm; }
  html, body { background: #fff !important; height: auto !important; overflow: visible !important; margin: 0 !important; }
  body > *:not(.status-print) { display: none !important; }
  .status-print {
    display: block; color: #1f2430; font-family: "Geist", system-ui, sans-serif; font-size: 9.5pt;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  .status-print h1 { margin: 0; font-size: 18pt; font-weight: 600; }
  .status-print .sp-date { margin: 1mm 0 5mm; font-size: 10.5pt; color: #566070; }
  .status-print table { width: 100%; border-collapse: collapse; }
  .status-print th, .status-print td { padding: 2mm; text-align: left; vertical-align: top; border: 0.3mm solid #b9c1cc; }
  .status-print thead { display: table-header-group; }
  .status-print thead th { background: #eef1f5; font-weight: 600; }
  .status-print tr { break-inside: avoid; page-break-inside: avoid; }
  .status-print .sp-no { width: 9mm; text-align: center; font-family: "Geist Mono", ui-monospace, monospace; font-variant-numeric: tabular-nums; }
  .status-print .sp-project { width: 34mm; }
  .status-print .sp-status { width: 30mm; }
  .status-print td strong, .status-print td span { display: block; }
  .status-print td span { color: #566070; }
  .status-print ul { margin: 0; padding-left: 4mm; }
  .status-print p { margin: 1mm 0 0; }
  .status-print .sp-facts { color: #566070; font-size: 8.5pt; }
  .status-print .sp-flag { font-weight: 600; }
}
`;
</script>
