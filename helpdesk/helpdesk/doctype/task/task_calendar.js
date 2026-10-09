// Copyright (c) 2026, Frappe Technologies and contributors
// For license information, please see license.txt

// Without this the Desk calendar looks for "start" / "end" columns, which Task doesn't have
frappe.views.calendar["Task"] = {
  field_map: {
    start: "exp_start_date",
    end: "exp_end_date",
    id: "name",
    title: "subject",
    allDay: "allDay",
  },
  gantt: true,
  filters: [
    {
      fieldtype: "Link",
      fieldname: "project",
      options: "Project",
      label: __("Project"),
    },
  ],
  get_events_method: "frappe.desk.calendar.get_events",
};
