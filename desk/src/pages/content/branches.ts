import { createResource } from "frappe-ui";
import { computed } from "vue";

export interface CustomerBranch {
  name: string;
  customer: string;
  branch_name: string;
  enabled: 0 | 1;
}

function branchList() {
  return createResource({
    url: "helpdesk.api.customer_branches.get_branches",
    cache: "content-customer-branches",
    auto: true,
  });
}

// one list for the whole app, so a branch added on the customer page shows up everywhere
let list: ReturnType<typeof branchList> | null = null;

/** Customers' branches (Roxy's Kochi, Kinassery…) for the content pages' pickers. */
export function useCustomerBranches() {
  list ??= branchList();
  const all = computed<CustomerBranch[]>(() => list!.data ?? []);

  /** The customer's branches; disabled ones only when `keep` is one of them. */
  function branchesOf(customer?: string | null, keep?: string | null) {
    if (!customer) return [];
    return all.value.filter(
      (b) => b.customer === customer && (b.enabled || b.name === keep)
    );
  }

  return { branches: all, branchesOf, reload: () => list!.reload() };
}
