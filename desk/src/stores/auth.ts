import { LOGIN_PAGE, router } from "@/router";
import { call, createResource } from "frappe-ui";
import { defineStore } from "pinia";
import { computed, ComputedRef, Ref, ref } from "vue";

const URI_LOGIN = "login";
const URI_LOGOUT = "logout";
const URI_USER_INFO = "helpdesk.api.auth.get_user";

/**
 * This is supposed to be the entry point of authentication. This will be
 * called from router itself. Hence the router instance from `useRouter()` will
 * not be available. All Authentication related logic should go in this file.
 * Some of these might contain async methods, beware. */
export const useAuthStore = defineStore("auth", () => {
  const userInfo = createResource({
    url: URI_USER_INFO,
  });
  const init = async () => {
    if (userInfo.fetched) return;
    await userInfo.fetch();
  };
  const reloadUser = userInfo.reload;

  const user__ = computed(() => userInfo.data || {});
  const hasDeskAccess: ComputedRef<boolean> = computed(
    () => user__.value.has_desk_access
  );
  const isAdmin: ComputedRef<boolean> = computed(() => user__.value.is_admin);
  const isAgent: ComputedRef<boolean> = computed(() => user__.value.is_agent);
  const hasAgentRecord: ComputedRef<boolean> = computed(
    () => user__.value.has_agent_record
  );
  const isManager: ComputedRef<boolean> = computed(
    () => user__.value.is_manager
  );
  const isProjectManager: ComputedRef<boolean> = computed(
    () => user__.value.is_project_manager
  );
  const canSeeOverview: ComputedRef<boolean> = computed(
    () => !!user__.value.can_see_overview
  );
  // the server allows the same people (helpdesk.api.customer_report)
  // writers, designers and marketers who only work on content
  const isContentTeam: ComputedRef<boolean> = computed(
    () => !!user__.value.is_content_team
  );
  // approves content posts after the client does (System Managers can too)
  const isDmHead: ComputedRef<boolean> = computed(
    () => !!user__.value.is_dm_head
  );
  // DM Coordinators, managers and System Managers; everyone else only attaches files
  const canEditContent: ComputedRef<boolean> = computed(
    () => !!user__.value.can_edit_content
  );
  // the only people who see the content calendar and content performance
  const inContentTeam: ComputedRef<boolean> = computed(
    () => !!user__.value.in_content_team
  );
  // ERP Employees: no work Calendar, and no Digital department (server side)
  const isErpOnly: ComputedRef<boolean> = computed(
    () => !!user__.value.is_erp_only
  );
  // DM Employees: no tickets, customers, contacts, templates, KB or reports
  const isDmEmployee: ComputedRef<boolean> = computed(
    () => !!user__.value.is_dm_employee
  );
  // the Tickets list and New ticket: System / Agent Managers and the ERP team
  const canWorkTickets: ComputedRef<boolean> = computed(
    () => !!user__.value.can_work_tickets
  );
  const canSeeCustomerReport: ComputedRef<boolean> = computed(
    () => !!(user__.value.is_manager || user__.value.is_project_manager)
  );
  const telephonyInstalled: ComputedRef<boolean> = computed(
    () => !!user__.value.telephony_installed
  );

  const userId: ComputedRef<string> = computed(() => user__.value.user_id);
  const userImage: ComputedRef<string> = computed(
    () => user__.value.user_image
  );
  const userFirstName: ComputedRef<string> = computed(
    () => user__.value.user_first_name
  );
  const userName: ComputedRef<string> = computed(() => user__.value.user_name);
  const username: ComputedRef<string> = computed(() => user__.value.username);
  const availability: ComputedRef<string> = computed(
    () => user__.value.availability || ""
  );
  const availabilityChangedOn: ComputedRef<string> = computed(
    () => user__.value.availability_changed_on || ""
  );
  const timezone: ComputedRef<string> = computed(() => user__.value.time_zone);
  const language: ComputedRef<string> = computed(() => user__.value.language);
  const userTeams: ComputedRef<string[]> = computed(
    () => user__.value.user_teams
  );
  const personaCaptured: ComputedRef<boolean> = computed(
    () => !!user__.value.persona_captured
  );

  function sessionUser() {
    const cookies = new URLSearchParams(document.cookie.split("; ").join("&"));
    let _sessionUser = cookies.get("user_id");
    if (_sessionUser === "Guest") {
      _sessionUser = null;
    }
    return _sessionUser;
  }
  const user: Ref<string> = ref(sessionUser());
  const isLoggedIn: ComputedRef<boolean> = computed(() => !!user.value);
  const login = createResource({
    url: URI_LOGIN,
    onError() {
      throw new Error("Invalid email or password");
    },
    onSuccess() {
      user.value = sessionUser();
      login.reset();
      router.replace({ path: "/" });
    },
  });

  function logout() {
    user.value = null;
    call(URI_LOGOUT).then(() => {
      window.location.href = LOGIN_PAGE;
    });
  }

  return {
    hasDeskAccess,
    init,
    isAdmin,
    isAgent,
    hasAgentRecord,
    isManager,
    isProjectManager,
    canSeeOverview,
    canSeeCustomerReport,
    isContentTeam,
    isDmHead,
    canEditContent,
    inContentTeam,
    isErpOnly,
    isDmEmployee,
    canWorkTickets,
    telephonyInstalled,
    isLoggedIn,
    login,
    reloadUser,
    userFirstName,
    userId,
    userImage,
    userName,
    username,
    availability,
    availabilityChangedOn,
    timezone,
    language,
    userTeams,
    personaCaptured,
    user,
    logout,
  };
});
