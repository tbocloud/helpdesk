import LucideContact2 from "~icons/lucide/contact-2";
import LucideTicket from "~icons/lucide/ticket";
import { OrganizationsIcon } from "../icons";
import LucideHome from "~icons/lucide/home";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideListTodo from "~icons/lucide/list-todo";
import LucideLayoutDashboard from "~icons/lucide/layout-dashboard";
import LucideClipboardList from "~icons/lucide/clipboard-list";
import LucideClock from "~icons/lucide/clock";
import LucideCalendarDays from "~icons/lucide/calendar-days";
import LucideChartColumn from "~icons/lucide/chart-column";
import LucideNewspaper from "~icons/lucide/newspaper";
import LucideUsers from "~icons/lucide/users";
import LucideFileSpreadsheet from "~icons/lucide/file-spreadsheet";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideHourglass from "~icons/lucide/hourglass";
import { __ } from "@/translation";

export const agentPortalSidebarOptions = [
  {
    label: __("Home"),
    icon: LucideHome,
    to: "Home",
    section: "Workspace",
  },
  {
    label: __("Overview"),
    icon: LucideLayoutDashboard,
    to: "WorkOverview",
    section: "Workspace",
    overviewOnly: true,
  },
  {
    label: __("Team"),
    icon: LucideUsers,
    to: "TeamWorkload",
    section: "Workspace",
    overviewOnly: true,
  },
  {
    label: __("Summaries"),
    icon: LucideNewspaper,
    to: "WorkSummaries",
    section: "Workspace",
    overviewOnly: true,
  },
  {
    label: __("Customer report"),
    icon: LucideFileSpreadsheet,
    to: "CustomerReport",
    section: "Workspace",
    customerReportOnly: true,
  },
  {
    label: __("Support hours"),
    icon: LucideHourglass,
    to: "SupportHours",
    section: "Workspace",
    customerReportOnly: true,
  },
  {
    label: __("Tickets"),
    icon: LucideTicket,
    to: "TicketsAgent",
    section: "Workspace",
    countKey: "tickets",
  },
  {
    label: __("Projects"),
    icon: LucideFolderKanban,
    to: "TaskyProjects",
    section: "Workspace",
  },
  {
    label: __("My Work"),
    icon: LucideListTodo,
    to: "MyWork",
    section: "Workspace",
    countKey: "my_work",
  },
  {
    label: __("Calendar"),
    icon: LucideCalendarClock,
    to: "WorkCalendar",
    section: "Workspace",
  },
  {
    label: __("Timesheets"),
    icon: LucideClock,
    to: "TaskyTimesheets",
    section: "Workspace",
  },
  {
    label: __("Performance"),
    icon: LucideChartColumn,
    to: "Performance",
    section: "Workspace",
  },
  {
    label: __("Content"),
    icon: LucideCalendarDays,
    to: "ContentCalendar",
    section: "Workspace",
  },
  {
    label: __("Customers"),
    icon: OrganizationsIcon,
    to: "CustomerList",
    section: "Directory",
  },
  {
    label: __("Contacts"),
    icon: LucideContact2,
    to: "ContactList",
    section: "Directory",
  },
  {
    label: __("Templates"),
    icon: LucideClipboardList,
    to: "TaskyTemplates",
    section: "Directory",
    projectManagerOnly: true,
  },
];

export const customerPortalSidebarOptions = [
  {
    label: __("Tickets"),
    icon: LucideTicket,
    to: "TicketsCustomer",
  },
];
