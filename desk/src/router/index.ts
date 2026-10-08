import { useScreenSize } from "@/composables/screen";
import { canViewPersona, personaInterrupt } from "@/persona";
import { useAuthStore } from "@/stores/auth";
import { useUserStore } from "@/stores/user";
import { isCustomerPortal } from "@/utils";
import { CONTENT_TEAM_ROUTES } from "@/pages/content/contentTeam";
import { createRouter, createWebHistory } from "vue-router";
const { isMobileView } = useScreenSize();

export const LOGIN_PAGE = "/login";

// type the meta fields
declare module "vue-router" {
  interface RouteMeta {
    auth?: boolean;
    agent?: boolean;
    admin?: boolean;
    public?: boolean;
    onSuccessRoute?: string;
    parent?: string;
  }
}

// Pages that render inside the portal chrome; PortalRoot picks the agent or
// customer shell from the session.
const portalRoutes = [
  // Agent Portal Routes
  {
    path: "",
    redirect: "/home",
  },
  {
    path: "/home",
    name: "Home",
    component: () => import("@/pages/home/Home.vue"),
  },

  {
    path: "/tickets",
    name: "TicketsAgent",
    component: () => import("@/pages/ticket/Tickets.vue"),
  },
  {
    path: "/tickets/:ticketId",
    name: "TicketAgent",
    component: () =>
      import(`@/pages/ticket/${handleMobileView("TicketAgent")}.vue`),
    props: true,
  },
  {
    path: "/tickets/new/:templateId?",
    name: "TicketAgentNew",
    component: () => import("@/pages/ticket/TicketNew.vue"),
    props: true,
    meta: {
      onSuccessRoute: "TicketAgent",
      parent: "TicketsAgent",
    },
  },
  {
    path: "/notifications",
    name: "Notifications",
    component: () => import("@/pages/MobileNotifications.vue"),
  },
  {
    path: "/kb",
    name: "AgentKnowledgeBase",
    component: () => import("@/pages/knowledge-base/KnowledgeBaseAgent.vue"),
  },
  {
    path: "/search",
    name: "SearchAgent",
    component: () => import("@/pages/SearchAgent.vue"),
    meta: { auth: true },
  },
  {
    path: "/kb/articles/:articleId",
    name: "Article",
    component: () => import("@/pages/knowledge-base/Article.vue"),
    props: true,
  },
  {
    path: "/articles/new/:id",
    name: "NewArticle",
    component: () => import("@/pages/knowledge-base/NewArticle.vue"),
    props: true,
  },
  {
    path: "/customers",
    name: "CustomerList",
    component: () => import("@/pages/customer/Customers.vue"),
  },
  {
    path: "/customers/:id",
    name: "Customer",
    component: () => import("@/pages/customer/Customer.vue"),
    props: true,
  },
  {
    path: "/contacts",
    name: "ContactList",
    component: () => import("@/pages/contact/Contacts.vue"),
  },
  {
    path: "/contacts/:id",
    name: "Contact",
    component: () => import("@/pages/contact/Contact.vue"),
    props: true,
  },
  {
    path: "/agents",
    name: "AgentList",
    redirect: "/tickets",
  },
  {
    path: "/teams",
    name: "Teams",
    redirect: "/tickets",
  },
  {
    path: "/teams/:teamId",
    name: "Team",
    redirect: "/tickets",
  },
  {
    path: "/dashboard",
    name: "Dashboard",
    redirect: "/home",
  },
  {
    path: "/content",
    name: "ContentCalendar",
    component: () => import("@/pages/content/ContentCalendar.vue"),
  },
  {
    path: "/content/report",
    name: "ContentReport",
    component: () => import("@/pages/content/ContentReport.vue"),
  },
  {
    path: "/content/plans",
    name: "ContentPlans",
    component: () => import("@/pages/content/ContentPlans.vue"),
  },
  {
    path: "/projects",
    name: "TaskyProjects",
    component: () => import("@/pages/tasky/Projects.vue"),
  },
  {
    path: "/templates",
    name: "TaskyTemplates",
    component: () => import("@/pages/tasky/Templates.vue"),
    beforeEnter: () => useAuthStore().isProjectManager || { name: "Home" },
  },
  {
    path: "/projects/:projectId",
    name: "TaskyProject",
    component: () => import("@/pages/tasky/PMDashboard.vue"),
    props: true,
  },
  {
    path: "/projects/:projectId/checklist",
    name: "TaskyChecklist",
    component: () => import("@/pages/tasky/Checklist.vue"),
    props: true,
  },
  {
    path: "/projects/:projectId/kanban",
    name: "TaskyKanban",
    component: () => import("@/pages/tasky/Kanban.vue"),
    props: true,
  },
  {
    path: "/projects/:projectId/timeline",
    name: "TaskyTimeline",
    component: () => import("@/pages/tasky/Timeline.vue"),
    props: true,
  },
  {
    path: "/projects/:projectId/overdue",
    name: "TaskyOverdue",
    component: () => import("@/pages/tasky/Overdue.vue"),
    props: true,
  },
  {
    path: "/projects/:projectId/files",
    name: "TaskyFiles",
    component: () => import("@/pages/tasky/ProjectFiles.vue"),
    props: true,
  },
  {
    path: "/projects/:projectId/signoff",
    name: "TaskySignoffs",
    component: () => import("@/pages/tasky/ProjectSignoffs.vue"),
    props: true,
  },
  {
    path: "/projects/:projectId/signoff/:signoffId",
    name: "TaskySignoff",
    component: () => import("@/pages/tasky/ProjectSignoff.vue"),
    props: true,
  },
  {
    path: "/my-tasks",
    name: "TaskyMyTasks",
    component: () => import("@/pages/tasky/MyTasks.vue"),
  },
  {
    path: "/my-work",
    name: "MyWork",
    component: () => import("@/pages/work/MyWork.vue"),
  },
  {
    path: "/overview",
    name: "WorkOverview",
    component: () => import("@/pages/work/Overview.vue"),
    beforeEnter: () => useAuthStore().canSeeOverview || { name: "Home" },
  },
  // everyone may open it; the server decides whose numbers they see
  {
    path: "/performance",
    name: "Performance",
    component: () => import("@/pages/performance/Performance.vue"),
  },
  {
    path: "/team",
    name: "TeamWorkload",
    component: () => import("@/pages/work/Team.vue"),
    beforeEnter: () => useAuthStore().canSeeOverview || { name: "Home" },
  },
  // not guarded like Overview: project managers without the Overview get
  // weekly reminders linking here, and the server filters what each user sees
  {
    path: "/work-summaries",
    name: "WorkSummaries",
    component: () => import("@/pages/work/WorkSummaries.vue"),
  },
  {
    path: "/calendar",
    name: "WorkCalendar",
    component: () => import("@/pages/work/WorkCalendar.vue"),
  },
  {
    path: "/customer-report",
    name: "CustomerReport",
    component: () => import("@/pages/work/CustomerReport.vue"),
    beforeEnter: () => useAuthStore().canSeeCustomerReport || { name: "Home" },
  },
  {
    path: "/work-summary/:name",
    name: "WorkSummary",
    component: () => import("@/pages/work/WorkSummary.vue"),
    props: true,
  },
  {
    path: "/timesheets",
    name: "TaskyTimesheets",
    component: () => import("@/pages/tasky/Timesheets.vue"),
  },
  {
    path: "/call-logs",
    name: "CallLogs",
    component: () => import("@/pages/call-logs/CallLogs.vue"),
  },

  // Customer Portal Routes
  {
    path: "/my-tickets",
    name: "TicketsCustomer",
    component: () => import("@/pages/ticket/Tickets.vue"),
    meta: {
      public: true,
      auth: true,
    },
  },
  {
    path: "/my-tickets/:ticketId",
    name: "TicketCustomer",
    component: () => import("@/pages/ticket/TicketCustomer.vue"),
    meta: {
      public: true,
      auth: true,
    },
    props: true,
  },
  {
    path: "/my-tickets/new",
    name: "TicketNew",
    component: () => import("@/pages/ticket/TicketNew.vue"),
    props: true,
    meta: {
      onSuccessRoute: "TicketCustomer",
      parent: "TicketsCustomer",
      public: true,
      auth: true,
    },
  },
  {
    path: "/kb-public",
    name: "CustomerKnowledgeBase",
    component: () => import("@/pages/knowledge-base/KnowledgeBaseCustomer.vue"),
    meta: {
      public: true,
      auth: true,
    },
  },
  {
    path: "/kb-public/:categoryId",
    name: "Articles",
    component: () => import("@/pages/knowledge-base/Articles.vue"),
    props: true,
    meta: {
      public: true,
      auth: true,
    },
  },
  {
    path: "/kb-public/articles/:articleId",
    name: "ArticlePublic",
    component: () => import("@/pages/knowledge-base/Article.vue"),
    props: true,
    meta: {
      public: true,
      auth: true,
    },
  },

  // Additonal routes
  {
    path: "/:pathMatch(.*)*",
    name: "Invalid Page",
    component: () => import("@/pages/InvalidPage.vue"),
  },
];

const routes = [
  // Renders bare — no portal chrome.
  {
    path: "/onboarding",
    name: "Persona",
    component: () => import("@/pages/PersonaForm.vue"),
    beforeEnter: () => canViewPersona(useAuthStore()) || { name: "Home" },
  },
  {
    path: "/",
    component: () => import("@/roots/PortalRoot.vue"),
    children: portalRoutes,
  },
];

const handleMobileView = (componentName: string) => {
  return isMobileView.value ? `Mobile${componentName}` : componentName;
};

export const router = createRouter({
  history: createWebHistory("/helpdesk/"),
  routes,
});

router.beforeEach(async (to, _, next) => {
  const authStore = useAuthStore();
  isCustomerPortal.value = to.meta.public || false;
  if (authStore.isLoggedIn) {
    await authStore.init();
  }

  const interrupt = personaInterrupt(to, authStore);
  if (interrupt) return next(interrupt);

  if (!authStore.isLoggedIn) {
    const redirectURL = to.fullPath !== "/" ? to.fullPath : "";

    window.location.href =
      LOGIN_PAGE +
      (redirectURL ? `?redirect-to=/helpdesk${redirectURL}` : "/helpdesk");
  } else if (!to.meta.public && !authStore.hasDeskAccess) {
    next({ name: "TicketsCustomer" });
  } else if (
    !to.meta.public &&
    authStore.isContentTeam &&
    !CONTENT_TEAM_ROUTES.has(String(to.name))
  ) {
    // writers and designers land on the content calendar, not tickets
    next({ name: "ContentCalendar" });
  } else if (to.name === "TicketAgent" && !authStore.isAgent) {
    const ticketId = to.params.ticketId;
    next({
      name: "TicketCustomer",
      params: { ticketId },
    });
  } else {
    next();
  }
});

router.afterEach(async (to) => {
  if (to.meta.public) return;
  const { users } = useUserStore();
  if (!users?.fetched) {
    await users.fetch();
  }
});
