<template>
  <!-- a due date on a day off: where it will be saved, before the task is saved -->
  <p
    v-if="move"
    class="flex items-start gap-1.5 text-p-xs text-info"
    role="status"
  >
    <LucideCalendarClock class="mt-px size-3.5 shrink-0" aria-hidden="true" />
    <span>
      {{
        __(
          "{0} is {1}, so the task will be due {2}.",
          dayjs(move.was).format("ddd D MMM"),
          move.reason,
          dayjs(move.due).format("ddd D MMM")
        )
      }}
    </span>
  </p>
</template>

<script setup lang="ts">
import { useDueDateMove } from "@/composables/workDays";
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import { toRef } from "vue";
import LucideCalendarClock from "~icons/lucide/calendar-clock";

const props = defineProps<{
  /** the due date picked, "YYYY-MM-DD" */
  date?: string | null;
  /** a content task: it moves to the working day before instead */
  content?: boolean;
}>();

const move = useDueDateMove(toRef(props, "date"), props.content);
</script>
