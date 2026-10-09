<template>
  <SettingsLayoutBase
    :title="__('CRM')"
    :description="
      __(
        'Connect TBO Support to the TBO CRM site: agents and customers on both, and support hours billed as ERPNext invoice drafts.'
      )
    "
    :dirty="isDirty"
    :saving="save.loading"
    :loading="!form && !settings.error"
    :error="settings.error"
    @retry="settings.reload()"
    @save="save.submit()"
  >
    <template #content>
      <div v-if="form">
        <SettingsSection
          :title="__('Connection')"
          :description="
            __(
              'On the CRM site, open a System Manager user → API Access → Generate Keys. Paste the keys here, never in chat or email.'
            )
          "
        >
          <FormControl
            v-model="form.site_url"
            :label="__('CRM site URL')"
            placeholder="https://tboindia.tbocloud.in"
          />
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormControl
              v-model="form.api_key"
              :label="__('API key')"
              autocomplete="off"
            />
            <FormControl
              v-model="form.api_secret"
              type="password"
              :label="__('API secret')"
              :placeholder="
                hasSecret ? __('Saved. Type a new one to replace it.') : ''
              "
              autocomplete="new-password"
            />
          </div>
          <Switch v-model="form.enabled" :label="__('Enabled')" />
          <div class="flex flex-wrap items-center gap-3">
            <Button
              :label="__('Test connection')"
              :loading="test.loading"
              :disabled="isDirty"
              :tooltip="isDirty ? __('Save your changes first') : ''"
              @click="test.submit()"
            >
              <template #prefix>
                <LucidePlugZap class="size-4" aria-hidden="true" />
              </template>
            </Button>
            <span
              v-if="test.data"
              role="status"
              class="inline-flex items-center gap-1.5 text-p-sm"
              :class="test.data.ok ? 'text-success' : 'text-danger'"
            >
              <component
                :is="test.data.ok ? LucideCircleCheck : LucideCircleAlert"
                class="size-4"
                aria-hidden="true"
              />
              {{ test.data.message }}
            </span>
          </div>
          <p v-if="isDirty" class="text-p-xs text-ink-gray-5">
            {{ __("Save your changes before testing the connection.") }}
          </p>
        </SettingsSection>

        <SettingsSection :title="__('Users')">
          <Switch
            v-model="form.sync_users"
            :label="__('Add helpdesk agents missing in the CRM')"
            :description="
              __(
                'Checked every hour and when an agent is added or leaves. Existing CRM users keep their roles.'
              )
            "
          />
          <Switch
            v-model="form.add_crm_users"
            :label="__('Add CRM users missing in helpdesk, as agents')"
            :description="__('Existing helpdesk users are left as they are.')"
          />
          <Switch
            v-model="form.disable_left_users"
            :label="__('Disable CRM users who leave helpdesk')"
            :description="
              __(
                'Only users this connection created in the CRM; people created there directly are never touched.'
              )
            "
          />
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormControl
              v-model="form.crm_role"
              type="select"
              :label="__('CRM role for new users')"
              :options="ROLES"
            />
          </div>
          <Switch
            v-model="form.send_welcome_email"
            :label="__('Send new users a welcome email to set their password')"
          />
        </SettingsSection>

        <SettingsSection :title="__('Customers')">
          <Switch
            v-model="form.sync_customers"
            :label="__('Sync customers both ways')"
            :description="
              __(
                'An HD Customer missing in the CRM becomes a CRM Organization, and the other way round. Matched by name; nothing existing is changed.'
              )
            "
          />
          <div class="flex flex-wrap items-center gap-3">
            <Button
              :label="__('Sync now')"
              :loading="sync.loading"
              :disabled="isDirty"
              :tooltip="isDirty ? __('Save your changes first') : ''"
              @click="sync.submit()"
            >
              <template #prefix>
                <LucideRefreshCw class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
          <p
            v-if="lastResult"
            class="text-p-sm"
            :class="lastFailed ? 'text-danger' : 'text-ink-gray-6'"
          >
            {{ lastResult }}
          </p>
        </SettingsSection>

        <SettingsSection
          :title="__('Invoicing')"
          :description="
            __(
              'Billable time becomes a draft Sales Invoice in ERPNext on the CRM site, from Support hours. Pick what it is billed as; the lists come from that site and are checked when you save.'
            )
          "
        >
          <p
            v-if="!connected"
            class="flex items-start gap-2 text-p-sm text-ink-gray-6"
          >
            <LucideInfo
              class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
            {{
              __(
                "Save the connection first; the companies and items are read from the CRM site."
              )
            }}
          </p>
          <template v-else>
            <div
              v-if="optionsProblem"
              role="alert"
              class="flex flex-wrap items-center gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
            >
              <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
              <span class="min-w-0 flex-1">
                {{
                  __(
                    "Couldn't read the lists from the CRM site: {0}",
                    optionsProblem
                  )
                }}
              </span>
              <Button :label="__('Try again')" @click="loadOptions()" />
            </div>
            <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <!-- Comboboxes: the item list can be long, and they can be searched -->
              <Combobox
                v-model="form.invoice_company"
                :label="__('Company')"
                :options="companyOptions"
                :loading="options.loading"
                :placeholder="__('Invoicing is off')"
                :empty-text="__('No company on the CRM site')"
              />
              <Combobox
                v-model="form.invoice_item"
                :label="__('Item the hours are billed as')"
                :options="itemOptions"
                :loading="options.loading"
                :placeholder="__('Pick a service item')"
                :empty-text="
                  __('No service item (a sales item that isn\'t stocked)')
                "
              />
              <FormControl
                v-model="form.invoice_hourly_rate"
                type="number"
                min="0"
                step="0.01"
                :label="__('Default hourly rate')"
                :description="
                  __('For customers without a contract rate per extra hour.')
                "
              />
              <Combobox
                v-model="form.invoice_currency"
                :label="__('Currency')"
                :options="currencyOptions"
                :loading="currencies.loading"
                :placeholder="__('Pick a currency')"
                :empty-text="__('No matching currency')"
              />
              <FormControl
                v-model="form.invoice_taxes_template"
                type="select"
                :label="__('Taxes template (optional)')"
                :options="optionalChoices('taxes_templates', 'title')"
                :disabled="!form.invoice_company"
              />
              <FormControl
                v-model="form.invoice_income_account"
                type="select"
                :label="__('Income account (optional)')"
                :description="__('Else the item\'s or company\'s default.')"
                :options="optionalChoices('income_accounts', 'account_name')"
                :disabled="!form.invoice_company"
              />
              <FormControl
                v-model="form.invoice_cost_center"
                type="select"
                :label="__('Cost center (optional)')"
                :options="optionalChoices('cost_centers', 'cost_center_name')"
                :disabled="!form.invoice_company"
              />
            </div>
            <p class="text-p-xs text-ink-gray-6">
              {{
                __(
                  "To turn invoicing off, clear the company; the item, template, account and cost center are cleared with it."
                )
              }}
            </p>
          </template>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  Combobox,
  createListResource,
  createResource,
  dayjs,
  FormControl,
  Switch,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideInfo from "~icons/lucide/info";
import LucidePlugZap from "~icons/lucide/plug-zap";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import SettingsSection from "../SettingsSection.vue";

interface CRMForm {
  enabled: boolean;
  site_url: string;
  api_key: string;
  api_secret: string;
  sync_users: boolean;
  crm_role: string;
  send_welcome_email: boolean;
  add_crm_users: boolean;
  disable_left_users: boolean;
  sync_customers: boolean;
  invoice_company: string;
  invoice_item: string;
  invoice_taxes_template: string;
  invoice_income_account: string;
  invoice_cost_center: string;
  invoice_hourly_rate: number | "";
  invoice_currency: string;
}

/** helpdesk.api.crm.get_invoicing_options: records on the CRM site's ERPNext */
interface InvoicingOptions {
  ok: boolean;
  message?: string;
  companies?: { name: string; default_currency?: string }[];
  items?: { name: string; item_name?: string }[];
  taxes_templates?: { name: string; title?: string }[];
  income_accounts?: { name: string; account_name?: string }[];
  cost_centers?: { name: string; cost_center_name?: string }[];
}

const DOCTYPE = "HD CRM Settings";
const ROLES = [
  { label: __("Sales User"), value: "Sales User" },
  { label: __("Sales Manager"), value: "Sales Manager" },
];

const form = ref<CRMForm | null>(null);
const initial = ref("");
const hasSecret = ref(false);
const lastSync = ref<{ on?: string; result?: string }>({});

// a new single has no saved value yet; these switches start on
function onByDefault(value: unknown) {
  return value === undefined || value === null ? true : Boolean(value);
}

const settings = createResource({
  url: "frappe.client.get",
  params: { doctype: DOCTYPE, name: DOCTYPE },
  auto: true,
  onSuccess(doc) {
    hasSecret.value = Boolean(doc.api_secret);
    lastSync.value = { on: doc.last_sync_on, result: doc.last_sync_result };
    form.value = {
      enabled: Boolean(doc.enabled),
      site_url: doc.site_url || "",
      api_key: doc.api_key || "",
      // the saved secret never comes back; only a newly typed one is sent
      api_secret: "",
      sync_users: doc.sync_users === undefined ? true : Boolean(doc.sync_users),
      crm_role: doc.crm_role || "Sales User",
      send_welcome_email:
        doc.send_welcome_email === undefined
          ? true
          : Boolean(doc.send_welcome_email),
      add_crm_users: onByDefault(doc.add_crm_users),
      disable_left_users: onByDefault(doc.disable_left_users),
      sync_customers: onByDefault(doc.sync_customers),
      invoice_company: doc.invoice_company || "",
      invoice_item: doc.invoice_item || "",
      invoice_taxes_template: doc.invoice_taxes_template || "",
      invoice_income_account: doc.invoice_income_account || "",
      invoice_cost_center: doc.invoice_cost_center || "",
      invoice_hourly_rate: doc.invoice_hourly_rate || "",
      invoice_currency: doc.invoice_currency || "",
    };
    initial.value = JSON.stringify(form.value);
    connected.value = Boolean(doc.site_url && doc.api_key && doc.api_secret);
    if (connected.value) loadOptions();
  },
});

// --- invoicing pickers, read live from the CRM site ---

const connected = ref(false);

const options = createResource({
  url: "helpdesk.api.crm.get_invoicing_options",
  makeParams: () => ({ company: form.value?.invoice_company || undefined }),
});
const optionsData = computed<InvoicingOptions | null>(
  () => options.data ?? null
);
const optionsProblem = computed(() =>
  options.error
    ? errorText(options.error, __("Check the connection and try again."))
    : optionsData.value && !optionsData.value.ok
    ? optionsData.value.message || ""
    : ""
);

function loadOptions() {
  options.reload().catch(() => {});
}

watch(
  () => form.value?.invoice_company,
  (company, previous) => {
    if (previous === undefined || !connected.value) return;
    loadOptions();
    // a new company's taxes, accounts and cost centers are its own
    if (form.value && company !== previous) {
      form.value.invoice_taxes_template = "";
      form.value.invoice_income_account = "";
      form.value.invoice_cost_center = "";
      // no company turns invoicing off; the server clears the item too
      if (!company) form.value.invoice_item = "";
      const currency = optionsData.value?.companies?.find(
        (c) => c.name === company
      )?.default_currency;
      if (currency && !form.value.invoice_currency)
        form.value.invoice_currency = currency;
    }
  }
);

/** the saved value stays listed while the lists load or if the CRM site lost it */
function withSaved(list: { value: string; label: string }[], saved: string) {
  return saved && !list.some((o) => o.value === saved)
    ? [{ value: saved, label: saved }, ...list]
    : list;
}

const companyOptions = computed(() =>
  withSaved(
    (optionsData.value?.companies ?? []).map((c) => ({
      value: c.name,
      label: c.name,
      description: c.default_currency,
    })),
    form.value?.invoice_company || ""
  )
);

const itemOptions = computed(() =>
  withSaved(
    (optionsData.value?.items ?? []).map((i) => ({
      value: i.name,
      label: i.item_name && i.item_name !== i.name ? i.item_name : i.name,
      description: i.name,
    })),
    form.value?.invoice_item || ""
  )
);

type CompanyList = "taxes_templates" | "income_accounts" | "cost_centers";
const FIELD_OF: Record<CompanyList, keyof CRMForm> = {
  taxes_templates: "invoice_taxes_template",
  income_accounts: "invoice_income_account",
  cost_centers: "invoice_cost_center",
};

function optionalChoices(list: CompanyList, titleField: string) {
  const rows = (optionsData.value?.[list] ?? []) as Record<string, string>[];
  return [
    { value: "", label: __("None") },
    ...withSaved(
      rows.map((r) => ({ value: r.name, label: r[titleField] || r.name })),
      String(form.value?.[FIELD_OF[list]] || "")
    ),
  ];
}

const currencies = createListResource({
  doctype: "Currency",
  filters: { enabled: 1 },
  fields: ["name"],
  orderBy: "name asc",
  pageLength: 500,
  auto: true,
});
const currencyOptions = computed(() =>
  (currencies.data ?? []).map((c: { name: string }) => ({
    label: c.name,
    value: c.name,
  }))
);

const isDirty = computed(
  () => !!form.value && JSON.stringify(form.value) !== initial.value
);

const save = createResource({
  url: "frappe.client.set_value",
  makeParams() {
    const f = form.value!;
    const fieldname: Record<string, unknown> = {
      ...f,
      enabled: f.enabled ? 1 : 0,
      sync_users: f.sync_users ? 1 : 0,
      send_welcome_email: f.send_welcome_email ? 1 : 0,
      add_crm_users: f.add_crm_users ? 1 : 0,
      disable_left_users: f.disable_left_users ? 1 : 0,
      sync_customers: f.sync_customers ? 1 : 0,
      invoice_hourly_rate: Number(f.invoice_hourly_rate) || 0,
    };
    if (!f.api_secret) delete fieldname.api_secret;
    return { doctype: DOCTYPE, name: DOCTYPE, fieldname };
  },
  onSuccess() {
    toast.success(__("CRM settings saved"));
    settings.reload();
  },
  onError(e: { messages?: string[] }) {
    toast.error(e.messages?.[0] || __("Couldn't save the CRM settings"));
  },
});

const test = createResource({
  url: "helpdesk.api.crm.test_connection",
  method: "POST",
});

const sync = createResource({
  url: "helpdesk.api.crm.sync_now",
  method: "POST",
  onSuccess(data: { ok: boolean; message: string }) {
    lastSync.value = { on: dayjs().format(), result: data.message };
    if (data.ok) toast.success(__("Synced with the CRM"));
    else toast.error(data.message || __("Some records couldn't be synced"));
  },
  onError(e: { messages?: string[] }) {
    toast.error(e.messages?.[0] || __("Couldn't sync users"));
  },
});

const lastResult = computed(() =>
  lastSync.value.result
    ? `${dayjs(lastSync.value.on).fromNow()}: ${lastSync.value.result}`
    : ""
);
const lastFailed = computed(() =>
  (lastSync.value.result || "").includes("Failed")
);
</script>
