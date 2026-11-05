import { __ } from "@/translation";
import type { Component } from "vue";
import { OrganizationsIcon } from "../icons";
import LucideBookOpen from "~icons/lucide/book-open";
import LucideBriefcase from "~icons/lucide/briefcase";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCalendarDays from "~icons/lucide/calendar-days";
import LucideCamera from "~icons/lucide/camera";
import LucideChartColumn from "~icons/lucide/chart-column";
import LucideClipboardList from "~icons/lucide/clipboard-list";
import LucideClock from "~icons/lucide/clock";
import LucideContact2 from "~icons/lucide/contact-2";
import LucideFileSpreadsheet from "~icons/lucide/file-spreadsheet";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideHandshake from "~icons/lucide/handshake";
import LucideHome from "~icons/lucide/home";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideLayoutDashboard from "~icons/lucide/layout-dashboard";
import LucideLifeBuoy from "~icons/lucide/life-buoy";
import LucideListTodo from "~icons/lucide/list-todo";
import LucideMessagesSquare from "~icons/lucide/messages-square";
import LucideNewspaper from "~icons/lucide/newspaper";
import LucideSquareKanban from "~icons/lucide/square-kanban";
import LucideTicket from "~icons/lucide/ticket";
import LucideTrophy from "~icons/lucide/trophy";
import LucideUsers from "~icons/lucide/users";
import LucideActivity from "~icons/lucide/activity";

/** A page in the sidebar. The flags are the role rules; see `isNavItemVisible`. */
export interface NavItem {
  id: string;
  label: string;
  icon: Component;
  /** route name */
  to: string;
  /** other routes of the same page (detail pages), so they keep it highlighted */
  also?: string[];
  /** key of `helpdesk.api.sidebar.get_nav_counts` shown as the badge */
  countKey?: string;
  ticketWorkersOnly?: boolean;
  leadsOnly?: boolean;
  leadBankOnly?: boolean;
  projectManagerOnly?: boolean;
  overviewOnly?: boolean;
  adoptionOnly?: boolean;
  customerReportOnly?: boolean;
}

/** A page in the tree under a parent item (a saved view). */
export interface NavChild {
  id: string;
  label: string;
  icon?: Component;
  to: { name: string; query?: Record<string, string> };
  view?: any;
  onSelect?: () => void;
}

/** An item that folds open to show a tree of sub-items. */
export interface NavTree {
  id: string;
  label: string;
  icon: Component;
  children: NavChild[];
}

export interface NavGroup {
  label?: string;
  items: NavItem[];
  trees?: NavTree[];
}

/** One icon in the rail; its groups are what the panel shows. */
export interface NavArea {
  id: string;
  label: string;
  icon: Component;
  groups: NavGroup[];
}

export const agentNavAreas: NavArea[] = [
  {
    id: "home",
    label: __("Home"),
    icon: LucideHome,
    groups: [
      {
        items: [
          { id: "home", label: __("Home"), icon: LucideHome, to: "Home" },
          // the async daily stand-up (docs/standup.md)
          {
            id: "standup",
            label: __("Stand-up"),
            icon: LucideMessagesSquare,
            to: "Standup",
          },
          // their own numbers and the champions; the server decides the rest
          {
            id: "scoreboard",
            label: __("Scoreboard"),
            icon: LucideTrophy,
            to: "TeamDashboard",
          },
        ],
      },
    ],
  },
  {
    id: "work",
    label: __("Work"),
    icon: LucideBriefcase,
    groups: [
      {
        label: __("My work"),
        items: [
          {
            id: "my-work",
            label: __("My Work"),
            icon: LucideListTodo,
            to: "MyWork",
            also: ["TaskyMyTasks"],
            countKey: "my_work",
          },
          // the person's own tasks from every project, as a board
          {
            id: "board",
            label: __("Board"),
            icon: LucideSquareKanban,
            to: "MyBoard",
          },
          // what's started across projects and content; members see their own
          {
            id: "in-progress",
            label: __("In progress"),
            icon: LucideActivity,
            to: "InProgress",
          },
          {
            id: "calendar",
            label: __("Calendar"),
            icon: LucideCalendarClock,
            to: "WorkCalendar",
          },
          {
            id: "timesheets",
            label: __("Timesheets"),
            icon: LucideClock,
            to: "TaskyTimesheets",
          },
        ],
      },
      {
        label: __("Projects"),
        items: [
          {
            id: "projects",
            label: __("Projects"),
            icon: LucideFolderKanban,
            to: "TaskyProjects",
            also: [
              "TaskyProject",
              "TaskyChecklist",
              "TaskyKanban",
              "TaskyTimeline",
              "TaskyOverdue",
              "TaskyRecurring",
              "TaskyFiles",
              "TaskyCredentials",
              "TaskyMeta",
              "TaskyAds",
              "TaskyCommission",
              "TaskySignoffs",
              "TaskySignoff",
              "ProjectStatus",
            ],
          },
          {
            id: "templates",
            label: __("Templates"),
            icon: LucideClipboardList,
            to: "TaskyTemplates",
            projectManagerOnly: true,
          },
        ],
      },
      {
        label: __("Team"),
        items: [
          {
            id: "overview",
            label: __("Overview"),
            icon: LucideLayoutDashboard,
            to: "WorkOverview",
            overviewOnly: true,
          },
          {
            id: "team",
            label: __("Team"),
            icon: LucideUsers,
            to: "TeamWorkload",
            overviewOnly: true,
          },
          {
            id: "adoption",
            label: __("Adoption"),
            icon: LucideActivity,
            to: "Adoption",
            adoptionOnly: true,
          },
        ],
      },
    ],
  },
  {
    id: "support",
    label: __("Support"),
    icon: LucideLifeBuoy,
    groups: [
      {
        items: [
          {
            id: "tickets",
            label: __("Tickets"),
            icon: LucideTicket,
            to: "TicketsAgent",
            also: ["TicketAgent", "TicketAgentNew"],
            countKey: "tickets",
            ticketWorkersOnly: true,
          },
          {
            id: "knowledge-base",
            label: __("Knowledge base"),
            icon: LucideBookOpen,
            to: "AgentKnowledgeBase",
            also: ["Article", "NewArticle", "SearchAgent"],
          },
        ],
      },
    ],
  },
  {
    id: "sales",
    label: __("Sales"),
    icon: LucideHandshake,
    groups: [
      {
        items: [
          // sales leads, live from the CRM site (docs/leads.md)
          {
            id: "leads",
            label: __("Leads"),
            icon: LucideHandshake,
            to: "Leads",
            also: ["Lead", "FindProspects", "LeadNewProposal", "LeadProposal"],
            leadsOnly: true,
          },
          // the Lead Bank: every active agent adds leads by photo (docs/lead-bank.md)
          {
            id: "lead-bank-add",
            label: __("Add a lead"),
            icon: LucideCamera,
            to: "LeadBankAdd",
            leadBankOnly: true,
          },
          {
            id: "lead-bank",
            label: __("My leads"),
            icon: LucideHandshake,
            to: "LeadBank",
            also: ["LeadBankTeam"],
            leadBankOnly: true,
          },
        ],
      },
    ],
  },
  {
    id: "content",
    label: __("Content"),
    icon: LucideCalendarDays,
    groups: [
      {
        items: [
          {
            id: "content-calendar",
            label: __("Content"),
            icon: LucideCalendarDays,
            to: "ContentCalendar",
            also: ["ContentReport", "ContentPlans"],
          },
          {
            id: "performance",
            label: __("Performance"),
            icon: LucideChartColumn,
            to: "Performance",
          },
        ],
      },
    ],
  },
  {
    id: "people",
    label: __("People"),
    icon: LucideUsers,
    groups: [
      {
        items: [
          {
            id: "customers",
            label: __("Customers"),
            icon: OrganizationsIcon,
            to: "CustomerList",
            also: ["Customer"],
          },
          {
            id: "contacts",
            label: __("Contacts"),
            icon: LucideContact2,
            to: "ContactList",
            also: ["Contact"],
          },
        ],
      },
    ],
  },
  {
    id: "reports",
    label: __("Reports"),
    icon: LucideChartColumn,
    groups: [
      {
        items: [
          {
            id: "summaries",
            label: __("Summaries"),
            icon: LucideNewspaper,
            to: "WorkSummaries",
            also: ["WorkSummary"],
            overviewOnly: true,
          },
          {
            id: "customer-report",
            label: __("Customer report"),
            icon: LucideFileSpreadsheet,
            to: "CustomerReport",
            customerReportOnly: true,
          },
          {
            id: "support-hours",
            label: __("Support hours"),
            icon: LucideHourglass,
            to: "SupportHours",
            customerReportOnly: true,
          },
        ],
      },
    ],
  },
];

export const customerNavAreas: NavArea[] = [
  {
    id: "support",
    label: __("Support"),
    icon: LucideLifeBuoy,
    groups: [
      {
        items: [
          {
            id: "tickets",
            label: __("Tickets"),
            icon: LucideTicket,
            to: "TicketsCustomer",
            also: ["TicketCustomer", "TicketNew"],
          },
          {
            id: "knowledge-base",
            label: __("Knowledge base"),
            icon: LucideBookOpen,
            to: "CustomerKnowledgeBase",
            also: ["Articles", "ArticlePublic"],
          },
        ],
      },
    ],
  },
];
