import LucideContact2 from "~icons/lucide/contact-2";
import LucideTicket from "~icons/lucide/ticket";
import LucideBookOpen from "~icons/lucide/book-open";
import { OrganizationsIcon } from "../icons";
import LucideHome from "~icons/lucide/home";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideListTodo from "~icons/lucide/list-todo";
import LucideSquareKanban from "~icons/lucide/square-kanban";
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
import LucideTrophy from "~icons/lucide/trophy";
import { __ } from "@/translation";

export const agentPortalSidebarOptions = [
  {
    label: __("Home"),
    icon: LucideHome,
    to: "Home",
    tone: "blue",
    section: "Workspace",
  },
  {
    label: __("Overview"),
    icon: LucideLayoutDashboard,
    to: "WorkOverview",
    tone: "blue",
    section: "Workspace",
    overviewOnly: true,
  },
  // everyone: their own numbers and the champions; the server decides the rest
  {
    label: __("Scoreboard"),
    icon: LucideTrophy,
    to: "TeamDashboard",
    tone: "blue",
    section: "Workspace",
  },
  {
    label: __("Team"),
    icon: LucideUsers,
    to: "TeamWorkload",
    tone: "teal",
    section: "Workspace",
    overviewOnly: true,
  },
  {
    label: __("Summaries"),
    icon: LucideNewspaper,
    to: "WorkSummaries",
    tone: "teal",
    section: "Workspace",
    overviewOnly: true,
  },
  {
    label: __("Customer report"),
    icon: LucideFileSpreadsheet,
    to: "CustomerReport",
    tone: "teal",
    section: "Workspace",
    customerReportOnly: true,
  },
  {
    label: __("Support hours"),
    icon: LucideHourglass,
    to: "SupportHours",
    tone: "orange",
    section: "Workspace",
    customerReportOnly: true,
  },
  {
    label: __("Tickets"),
    icon: LucideTicket,
    to: "TicketsAgent",
    tone: "orange",
    section: "Workspace",
    countKey: "tickets",
    ticketWorkersOnly: true,
  },
  {
    label: __("Projects"),
    icon: LucideFolderKanban,
    to: "TaskyProjects",
    tone: "purple",
    section: "Workspace",
  },
  {
    label: __("My Work"),
    icon: LucideListTodo,
    to: "MyWork",
    tone: "purple",
    section: "Workspace",
    countKey: "my_work",
  },
  {
    // the person's own tasks from every project, as a board
    label: __("Board"),
    icon: LucideSquareKanban,
    to: "MyBoard",
    tone: "purple",
    section: "Workspace",
  },
  {
    label: __("Calendar"),
    icon: LucideCalendarClock,
    to: "WorkCalendar",
    tone: "green",
    section: "Workspace",
  },
  {
    label: __("Timesheets"),
    icon: LucideClock,
    to: "TaskyTimesheets",
    tone: "green",
    section: "Workspace",
  },
  {
    label: __("Performance"),
    icon: LucideChartColumn,
    to: "Performance",
    tone: "blue",
    section: "Workspace",
  },
  {
    label: __("Content"),
    icon: LucideCalendarDays,
    to: "ContentCalendar",
    tone: "purple",
    section: "Workspace",
  },
  {
    label: __("Customers"),
    icon: OrganizationsIcon,
    to: "CustomerList",
    tone: "blue",
    section: "Directory",
  },
  {
    label: __("Contacts"),
    icon: LucideContact2,
    to: "ContactList",
    tone: "teal",
    section: "Directory",
  },
  {
    label: __("Templates"),
    icon: LucideClipboardList,
    to: "TaskyTemplates",
    tone: "purple",
    section: "Directory",
    projectManagerOnly: true,
  },
  {
    label: __("Knowledge base"),
    icon: LucideBookOpen,
    to: "AgentKnowledgeBase",
    tone: "green",
    section: "Directory",
  },
];

export const customerPortalSidebarOptions = [
  {
    label: __("Tickets"),
    icon: LucideTicket,
    to: "TicketsCustomer",
  },
  {
    label: __("Knowledge base"),
    icon: LucideBookOpen,
    to: "CustomerKnowledgeBase",
  },
];
