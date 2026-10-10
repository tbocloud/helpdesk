import { __ } from "@/translation";
import { createResource, dayjs } from "frappe-ui";

/** helpdesk.api.calendar.get_on_leave: approved leave synced from the CRM site */
export interface LeaveToday {
  to_date: string;
  half_day: boolean;
}

// one request per page load, shared by every picker and team view
const onLeave = createResource({
  url: "helpdesk.api.calendar.get_on_leave",
  onError() {},
});

/** "On leave until Wed 14 Oct", "On leave today" or "Half day today". */
function leaveText(leave: LeaveToday | null | undefined): string {
  if (!leave) return "";
  if (leave.half_day) return __("Half day today");
  const to = dayjs(leave.to_date);
  return to.isSame(dayjs(), "day")
    ? __("On leave today")
    : __("On leave until {0}", to.format("ddd D MMM"));
}

/**
 * Who is on leave today, for the assignee pickers and the team views. A failed load
 * shows nobody as away rather than blocking the picker.
 */
export function useOnLeave() {
  if (!onLeave.data && !onLeave.loading) onLeave.fetch();

  function leaveOf(user: string | null | undefined): LeaveToday | null {
    return (user && (onLeave.data as Record<string, LeaveToday>)?.[user]) || null;
  }

  return {
    leaveOf,
    /** The marker text for `user`, or "" when they're working. */
    leaveLabel: (user: string | null | undefined) => leaveText(leaveOf(user)),
  };
}
