/** Working days on the desk: a task is never due on a day off and never goes overdue over
 * one (server: helpdesk.work_calendar, "days off and task due dates"). */

import { call, createResource, dayjs } from "frappe-ui";
import { ref, watch, type Ref } from "vue";

const cutoff = createResource({
  url: "helpdesk.api.work_days.get_overdue_cutoff",
  cache: "overdue-cutoff",
});
let asked = "";

/** A task due before this day is overdue: today, or the first of the days off right before
 * it, as the server counts. Read once a day; until it is in, today. Another day than today
 * counts from that day. */
export function overdueCutoff(now = dayjs()) {
  const today = dayjs().format("YYYY-MM-DD");
  if (asked !== today) {
    asked = today;
    cutoff.fetch();
  }
  const server = cutoff.data?.cutoff as string | undefined;
  return server && now.isSame(dayjs(), "day") ? dayjs(server) : now;
}

export interface DueDateMove {
  /** the date picked */
  was: string;
  /** where it will be saved */
  due: string;
  /** why the picked day is off: "Onam", "a weekly off", "a Saturday off" */
  reason: string;
}

/** Where the due date picked will be saved when it falls on a day off (null on a working
 * day), asked again whenever the date changes. `content`: a content task, which moves to the
 * working day before its post goes live instead. */
export function useDueDateMove(
  date: Ref<string | null | undefined>,
  content = false
) {
  const move = ref<DueDateMove | null>(null);
  let latest = 0;
  watch(
    date,
    async (value) => {
      const ask = ++latest;
      move.value = null;
      if (!value) return;
      try {
        const answer = await call("helpdesk.api.work_days.check_due_date", {
          date: value,
          content: content ? 1 : 0,
        });
        if (ask === latest) move.value = answer || null;
      } catch {
        // only a hint: the server moves the date when the task is saved anyway
      }
    },
    { immediate: true }
  );
  return move;
}
