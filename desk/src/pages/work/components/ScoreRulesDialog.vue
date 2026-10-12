<template>
  <!-- "How weight works": the numbers come from the server's formula (team_dashboard.score_rules) -->
  <Dialog
    v-model:open="open"
    :options="{ title: __('How weight and quality work'), size: 'xl' }"
  >
    <template #body-content>
      <div class="flex flex-col gap-5 text-p-sm text-ink-gray-7">
        <section aria-labelledby="rules-weight">
          <h3 id="rules-weight" class="text-base-medium text-ink-gray-9">
            {{ __("Weight: how big the task is") }}
          </h3>
          <p class="mt-1">
            {{
              __(
                "Nobody types a weight; it comes from the task itself, from {0} to {1}.",
                num(rules.weight.min),
                num(rules.weight.max)
              )
            }}
          </p>
          <dl class="mt-2 flex flex-col gap-1">
            <div v-for="row in weightRows" :key="row.label" :class="ROW">
              <dt>{{ row.label }}</dt>
              <dd class="shrink-0 font-mono tabular-nums text-ink-gray-9">
                {{ row.value }}
              </dd>
            </div>
          </dl>
          <p class="mt-2">
            {{
              __(
                "Self-assigned: a task you made and took yourself starts at {0}, and its key flag and priority don't count; its estimate counts up to {1} hours. Ask the lead to assign work that matters.",
                num(rules.weight.self_made_base),
                num(
                  rules.weight.self_made_size_cap / rules.weight.size_per_hour
                )
              )
            }}
          </p>
          <p class="mt-1">
            {{ __("Hours you log never change a task's weight.") }}
          </p>
        </section>

        <section aria-labelledby="rules-quality">
          <h3 id="rules-quality" class="text-base-medium text-ink-gray-9">
            {{ __("Quality: how well it was done") }}
          </h3>
          <p class="mt-1">
            {{
              __(
                "When a task is done, whoever assigned or reviewed it (never the person who did it) may rate it. Rating is optional; an unrated task counts ×{0}.",
                num(rules.quality.unrated)
              )
            }}
          </p>
          <dl class="mt-2 flex flex-col gap-1">
            <div v-for="row in qualityRows" :key="row.label" :class="ROW">
              <dt>{{ row.label }}</dt>
              <dd class="shrink-0 font-mono tabular-nums text-ink-gray-9">
                {{ row.value }}
              </dd>
            </div>
          </dl>
          <p class="mt-2">
            {{
              __(
                "Quality stays between ×{0} and ×{1}.",
                num(rules.quality.floor),
                num(rules.quality.ceiling)
              )
            }}
          </p>
        </section>

        <section aria-labelledby="rules-score">
          <h3 id="rules-score" class="text-base-medium text-ink-gray-9">
            {{ __("The score") }}
          </h3>
          <p class="mt-1">
            {{
              __(
                "Each task earns its weight × its quality: half for finishing it, half for finishing it by its due date. Overdue work costs {0} a task and moving a due date {1}; hours add a little, capped.",
                num(rules.score.overdue),
                num(rules.score.slip)
              )
            }}
          </p>
          <p
            class="mt-2 rounded-md bg-surface-gray-2 px-3 py-2 text-ink-gray-8"
          >
            {{ example }}
          </p>
          <p class="mt-2">
            {{
              __(
                "To be champion this period: at least {0} weighted work from at least {1} tasks or posts.",
                num(rules.champion_minimum),
                String(rules.min_delivered)
              )
            }}
          </p>
        </section>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Dialog } from "frappe-ui";
import { computed } from "vue";
import type { ScoreRules } from "../teamDashboardMeta";

const props = defineProps<{ rules: ScoreRules }>();
const open = defineModel<boolean>("open", { default: false });

const ROW = "flex items-baseline justify-between gap-3";

/** Signed and without trailing zeros: "+1", "−0.25", "4.5". */
function num(value: number, signed = false) {
  const text = String(Math.round(Math.abs(value) * 1000) / 1000);
  if (!signed) return value < 0 ? `−${text}` : text;
  return `${value < 0 ? "−" : "+"}${text}`;
}

const weightRows = computed(() => {
  const w = props.rules.weight;
  return [
    { label: __("Every task"), value: num(w.base) },
    { label: __("Key task or milestone"), value: num(w.key, true) },
    {
      label: __(
        "Estimate, per hour (up to {0} hours)",
        num(w.size_cap / w.size_per_hour)
      ),
      value: num(w.size_per_hour, true),
    },
    ...Object.entries(w.priority).map(([priority, bonus]) => ({
      label: __("{0} priority", __(priority)),
      value: num(bonus, true),
    })),
  ];
});

const qualityRows = computed(() => {
  const q = props.rules.quality;
  return [
    ...Object.entries(q.rating)
      .sort((a, b) => b[1] - a[1])
      .map(([rating, factor]) => ({
        label: __("Rated {0}", __(rating)),
        value: `×${num(factor)}`,
      })),
    { label: __("Each send-back on review"), value: num(q.sent_back, true) },
    {
      label: __(
        "Each time it came back after it was done (task or its ticket reopened)"
      ),
      value: num(q.came_back, true),
    },
  ];
});

// a worked example from the same numbers
const example = computed(() => {
  const w = props.rules.weight;
  const q = props.rules.quality;
  const weight = w.base + w.key + 8 * w.size_per_hour + (w.priority.High || 0);
  const excellent = q.rating.Excellent ?? 1;
  return __(
    "Example: a key task estimated at 8 hours, High priority, weighs {0}. Rated Excellent and done on time it earns {1}; done late, {2}.",
    num(weight),
    num(Math.round(weight * excellent * 10) / 10),
    num(Math.round(weight * excellent * props.rules.score.done_share * 10) / 10)
  );
});
</script>
