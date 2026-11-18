<template>
  <!-- a KPI (a Text target): ticked off by the person, then confirmed by a Sales Head -->
  <div class="flex min-w-0 flex-col gap-2">
    <p class="flex flex-wrap items-center gap-x-1.5 text-xs" :class="look.ink">
      <component :is="look.icon" class="size-3.5 shrink-0" aria-hidden="true" />
      <span class="font-medium">{{ look.text }}</span>
      <span v-if="criterion.kpi_done_on" class="text-ink-gray-6 tabular-nums">
        · {{ dayjs(criterion.kpi_done_on).format("D MMM") }}
      </span>
    </p>
    <blockquote
      v-if="criterion.kpi_note"
      class="whitespace-pre-line break-words border-l-2 border-outline-gray-3 pl-2.5 text-p-sm text-ink-gray-7"
    >
      {{ criterion.kpi_note }}
    </blockquote>

    <!-- the person ticks it off, with what they did -->
    <form
      v-if="writing"
      class="flex flex-col gap-2"
      @submit.prevent="send({ done: 1, note })"
    >
      <FormControl
        v-model="note"
        type="textarea"
        :rows="2"
        :label="__('What did you do? (optional)')"
        :placeholder="__('e.g. Published 3 case studies on the blog')"
      />
      <div class="flex gap-2">
        <Button
          type="submit"
          variant="solid"
          :label="__('Mark as done')"
          :loading="saving"
        />
        <Button :label="__('Cancel')" @click="writing = false" />
      </div>
    </form>
    <div v-else-if="action" class="flex">
      <Button :label="action.label" :loading="saving" @click="action.run">
        <template #prefix>
          <component :is="action.icon" class="size-4" />
        </template>
      </Button>
    </div>

    <ErrorMessage v-if="error" :message="error" role="alert" />
    <p class="text-xs text-ink-gray-6">
      {{
        __(
          "Counts once it's marked done and a Sales Head confirms it. Until then it counts 0% of the month."
        )
      }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, dayjs, ErrorMessage, FormControl } from "frappe-ui";
import { computed, ref } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideClock from "~icons/lucide/clock";
import LucideUndo2 from "~icons/lucide/undo-2";
import type { Criterion, Target } from "./salesTargets";

const props = defineProps<{
  criterion: Criterion;
  month: string;
  /** person: their own KPI, to tick off; head: someone's, to confirm */
  mode: "person" | "head";
  /** whose KPI, for a head */
  employee?: string;
}>();
const emit = defineEmits<{ changed: [target: Target] }>();

const writing = ref(false);
const note = ref("");
const saving = ref(false);
const error = ref("");

const look = computed(() => {
  const status = props.criterion.kpi_status;
  if (status === "Confirmed")
    return {
      icon: LucideCircleCheck,
      ink: "text-success",
      text: __(
        "Confirmed by {0}",
        props.criterion.kpi_confirmed_by_name ||
          props.criterion.kpi_confirmed_by ||
          ""
      ),
    };
  if (status === "Done")
    return {
      icon: LucideClock,
      ink: "text-info",
      text:
        props.mode === "person"
          ? __("Marked done, waiting for your Sales Head")
          : __("Marked done, waiting for you to confirm"),
    };
  return {
    icon: LucideCircleDashed,
    ink: "text-ink-gray-6",
    text: __("Not done yet"),
  };
});

const action = computed(() => {
  const status = props.criterion.kpi_status;
  if (props.mode === "person") {
    if (!status)
      return {
        label: __("Mark as done"),
        icon: LucideCheck,
        run: () => (writing.value = true),
      };
    if (status === "Done")
      return {
        label: __("Not done after all"),
        icon: LucideUndo2,
        run: () => send({ done: 0 }),
      };
    return null;
  }
  if (status === "Done")
    return {
      label: __("Confirm it's done"),
      icon: LucideCheck,
      run: () => send({ confirmed: 1 }),
    };
  if (status === "Confirmed")
    return {
      label: __("Reopen"),
      icon: LucideUndo2,
      run: () => send({ confirmed: 0 }),
    };
  return null;
});

async function send(args: Record<string, unknown>) {
  if (saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    const target =
      props.mode === "person"
        ? await call("helpdesk.api.sales_targets.mark_kpi_done", {
            month: props.month,
            criterion: props.criterion.criterion,
            ...args,
          })
        : await call("helpdesk.api.sales_targets.confirm_kpi", {
            month: props.month,
            employee: props.employee,
            criterion: props.criterion.criterion,
            ...args,
          });
    writing.value = false;
    note.value = "";
    emit("changed", target);
  } catch (e) {
    error.value = errorText(
      e,
      __("Couldn't save that. Check your connection and try again.")
    );
  } finally {
    saving.value = false;
  }
}
</script>
