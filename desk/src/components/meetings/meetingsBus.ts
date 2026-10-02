import { createResource } from "frappe-ui";
import { ref } from "vue";

// bumped when a meeting is scheduled outside the Meetings card (e.g. from the
// ticket header), so the card reloads
export const meetingsChanged = ref(0);

// cached for the session: the header checks it on every ticket
export const meetingsEnabled = createResource({
  url: "helpdesk.api.meetings.meetings_enabled",
  cache: "helpdesk:meetings-enabled",
  auto: true,
});
