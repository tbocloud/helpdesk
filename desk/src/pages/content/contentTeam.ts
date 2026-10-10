// What a Content Team member (writer, designer, marketer) can open: the
// content calendar, their projects and tasks, their calendar and timesheets,
// and their own content performance.
// The content calendar's pages and its performance report: only the content
// team sees them (authStore.inContentTeam, docs/content-calendar.md)
export const CONTENT_ROUTES = new Set([
  "ContentCalendar",
  "ContentReport",
  "ContentPlans",
  "Performance",
]);

// Hidden from DM and ERP Employees, who work on projects and content, not support
export const DEPARTMENT_EMPLOYEE_HIDDEN_ROUTES = new Set([
  "SupportHours",
  "CustomerReport",
  "TicketsAgent",
  "TicketAgent",
  "TicketAgentNew",
  "CustomerList",
  "Customer",
  "ContactList",
  "Contact",
  "TaskyTemplates",
  "AgentKnowledgeBase",
  "Article",
  "NewArticle",
]);

// Also hidden from ERP Employees, who are never in the content team
export const ERP_EMPLOYEE_HIDDEN_ROUTES = new Set(["WorkCalendar"]);

export const CONTENT_TEAM_ROUTES = new Set([
  "ContentCalendar",
  "ContentReport",
  "Performance",
  "TaskyProjects",
  "TaskyProject",
  "TaskyChecklist",
  "TaskyKanban",
  "TaskyTimeline",
  "TaskyOverdue",
  "TaskyMyTasks",
  "MyWork",
  "MyBoard",
  "WorkCalendar",
  "TaskyTimesheets",
  "Notifications",
]);
