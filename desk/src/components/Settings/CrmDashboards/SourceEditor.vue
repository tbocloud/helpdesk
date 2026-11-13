<template>
  <SettingsLayoutBase
    :title="name || __('New data source')"
    :back-label="__('Back to CRM dashboards')"
    :dirty="dirty"
    :save-label="name ? __('Save changes') : __('Create source')"
    :save-disabled="name ? !dirty : !form.source_name.trim()"
    :saving="saving"
    :loading="!!name && source.loading && !source.data"
    :error="source.error"
    @retry="source.reload()"
    @back="back"
    @save="save"
  >
    <template #header-actions>
      <Switch v-model="form.enabled" size="sm" :label="__('Enabled')" />
    </template>
    <template #content>
      <div class="flex flex-col">
        <SettingsSection :title="__('Details')">
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormControl
              v-model="form.source_name"
              :label="__('Name')"
              :description="
                name
                  ? __('Fixed once saved.')
                  : __('The company or site, e.g. TBO India.')
              "
              :disabled="!!name"
              maxlength="140"
              required
            />
            <FormControl
              v-model="form.company_label"
              :label="__('Company for leads without one')"
              :description="
                __(
                  'Leads with no company, or all of them when no company field is mapped.'
                )
              "
              maxlength="140"
            />
            <FormControl
              v-model="form.lead_doctype"
              :label="__('Lead document type')"
              :description="__('Lead on ERPNext, CRM Lead on Frappe CRM.')"
              maxlength="140"
            />
          </div>
        </SettingsSection>

        <SettingsSection
          :title="__('Connection')"
          :description="
            __(
              'An API key of a user there who may read its leads. The secret stays on the server.'
            )
          "
        >
          <Switch
            v-model="form.use_crm_connection"
            :label="__('Use the CRM connection')"
            :description="
              crmConnection.site_url
                ? __(
                    'Read {0} with the key in Settings → CRM.',
                    crmConnection.site_url
                  )
                : __('Set up the connection in Settings → CRM first.')
            "
            :disabled="!crmConnection.site_url"
          />
          <div
            v-if="!form.use_crm_connection"
            class="grid grid-cols-1 gap-4 sm:grid-cols-2"
          >
            <FormControl
              v-model="form.site_url"
              type="url"
              :label="__('Site URL')"
              placeholder="https://erp.example.com"
              autocomplete="off"
            />
            <FormControl
              v-model="form.api_key"
              :label="__('API key')"
              autocomplete="off"
            />
            <SecretField
              v-model="secret"
              class="sm:col-span-2"
              :label="__('API secret')"
              :status="source.data?.api_secret || { set: false, masked: '' }"
            />
          </div>
          <SettingsAction
            v-if="name"
            method="helpdesk.api.crm_dashboard_settings.test_source"
            :params="{ name }"
            :label="__('Test connection')"
            :icon="LucidePlugZap"
            :unsaved="dirty"
            @done="remoteFields.reload()"
          />
        </SettingsSection>

        <SettingsSection
          :title="__('Money')"
          :description="
            __(
              'The currency its amounts are in, and what one is worth in the reporting currency.'
            )
          "
        >
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div class="flex flex-col gap-1.5">
              <FormLabel :label="__('Currency')" size="md" />
              <Link
                v-model="form.currency"
                doctype="Currency"
                :placeholder="__('Pick a currency')"
              />
            </div>
            <FormControl
              v-model="form.exchange_rate"
              type="number"
              min="0"
              step="any"
              :label="
                __(
                  '1 {0} in {1}',
                  form.currency || __('this currency'),
                  reportingCurrency || __('the reporting currency')
                )
              "
              :disabled="
                !!reportingCurrency && form.currency === reportingCurrency
              "
              :description="
                reportingCurrency
                  ? __('Kept at 1 when it is the reporting currency.')
                  : __('Set the reporting currency on the previous page.')
              "
            />
          </div>
        </SettingsSection>

        <SettingsSection
          :title="__('Field mapping')"
          :description="
            __(
              'Which of its lead fields hold each value. Leave one empty when it has none: a team, for example, can come from the organisation instead.'
            )
          "
        >
          <p
            v-if="mappingNote"
            class="flex items-start gap-2 rounded-md bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-7"
          >
            <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span>{{ mappingNote }}</span>
          </p>
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <template
              v-for="(meta, target) in registry.mapped_fields"
              :key="target"
            >
              <FormControl
                v-if="fieldOptions"
                v-model="form[target]"
                type="select"
                :label="meta.label"
                :required="registry.required_fields.includes(target)"
                :options="optionsFor(target, meta.kind)"
              />
              <FormControl
                v-else
                v-model="form[target]"
                :label="meta.label"
                :required="registry.required_fields.includes(target)"
                :placeholder="__('Field name, e.g. {0}', example(meta.kind))"
                autocomplete="off"
              />
            </template>
          </div>
        </SettingsSection>

        <SettingsSection
          :title="__('Status mapping')"
          :description="
            __(
              'Which reporting category each of its statuses counts as. A status with none counts in Total leads only. Pick a company to map a status for that company alone.'
            )
          "
        >
          <div
            v-if="unmapped.length"
            class="flex flex-col gap-2 rounded-md bg-warning-soft px-3 py-2 text-p-sm text-warning"
            role="status"
          >
            <span class="flex items-center gap-2">
              <LucideTriangleAlert class="size-4 shrink-0" aria-hidden="true" />
              {{ __("These statuses have no category yet:") }}
            </span>
            <div class="flex flex-wrap gap-2">
              <Button
                v-for="status in unmapped"
                :key="status.status"
                :label="
                  status.leads
                    ? __(
                        'Map {0} ({1} leads)',
                        status.status,
                        String(status.leads)
                      )
                    : __('Map {0}', status.status)
                "
                @click="addStatus(status.status)"
              />
            </div>
          </div>
          <ul class="flex flex-col gap-2" :aria-label="__('Status mapping')">
            <li
              v-for="(row, i) in form.status_map"
              :key="i"
              class="grid grid-cols-1 items-end gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]"
            >
              <FormControl
                v-model="row.status"
                :label="__('Lead status')"
                autocomplete="off"
              />
              <FormControl
                v-model="row.category"
                type="select"
                :label="__('Counts as')"
                :placeholder="__('Pick a category')"
                :options="categoryOptions"
              />
              <FormControl
                v-model="row.company"
                :label="__('Only for company')"
                :placeholder="__('Every company')"
                autocomplete="off"
              />
              <Button
                variant="ghost"
                class="sm:mb-0.5"
                :aria-label="__('Remove {0}', row.status || __('this row'))"
                @click="form.status_map.splice(i, 1)"
              >
                <template #icon>
                  <LucideX class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </li>
          </ul>
          <div>
            <Button :label="__('Add status')" @click="addStatus('')">
              <template #prefix>
                <LucidePlus class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
        </SettingsSection>

        <SettingsSection
          :title="__('Sync')"
          :description="
            __(
              'The hub copies the mapped fields of its leads, and only those. Every night it reads them all again, which drops the leads deleted there.'
            )
          "
        >
          <FormControl
            v-model="form.sync_every"
            type="select"
            class="w-full sm:w-56"
            :label="__('Read changes every')"
            :options="SYNC_EVERY"
          />
          <template v-if="source.data">
            <p class="text-p-sm tabular-nums text-ink-gray-7">
              {{ syncSummary(source.data, (d) => dayjs(d).fromNow()) }}
            </p>
            <div
              v-if="source.data.last_sync_status === 'Failed'"
              role="alert"
              class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
            >
              <LucideCircleAlert
                class="mt-0.5 size-4 shrink-0"
                aria-hidden="true"
              />
              <span class="min-w-0 flex-1 break-words">{{
                source.data.last_error
              }}</span>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <Button
                :label="__('Sync now')"
                :loading="syncing"
                :disabled="dirty || !form.enabled || source.data.running"
                @click="syncNow(false)"
              />
              <Button
                variant="ghost"
                :label="__('Read every lead again')"
                :disabled="dirty || !form.enabled || source.data.running"
                @click="syncNow(true)"
              />
              <span v-if="dirty" class="text-p-xs text-ink-gray-6">
                {{ __("Save your changes first.") }}
              </span>
            </div>
          </template>
        </SettingsSection>

        <ConfigHistory
          v-if="name"
          doctype="HD CRM Source"
          :name="name"
          :version="source.data?.modified"
        />

        <SettingsSection
          v-if="name"
          :title="__('Delete source')"
          :description="
            __(
              'Removes its copied leads and its organisation from the hub. Nothing changes on its site. To stop counting it for now, switch it off instead.'
            )
          "
        >
          <div>
            <Button
              theme="red"
              :label="__('Delete source')"
              @click="deleteOpen = true"
            />
          </div>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>

  <Dialog v-model:open="deleteOpen" :title="__('Delete {0}?', name)" size="sm">
    <p class="text-p-sm text-ink-gray-7">
      {{
        __(
          "Every dashboard stops counting its leads, and its units leave the dashboards they were picked on. This can't be undone."
        )
      }}
    </p>
    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          theme="red"
          variant="solid"
          :label="__('Delete source')"
          :loading="deleting"
          @click="remove"
        />
      </div>
    </template>
  </Dialog>
  <ConfirmDialog
    v-model="confirmLeave"
    :title="__('Leave without saving?')"
    :message="
      __('Your changes on this page haven\'t been saved and will be lost.')
    "
    :on-confirm="() => emit('back')"
    :on-cancel="() => (confirmLeave = false)"
  />
</template>

<script setup lang="ts">
import { Link } from "@/components";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useIntervalFn } from "@vueuse/core";
import {
  Button,
  call,
  createResource,
  dayjs,
  Dialog,
  FormControl,
  FormLabel,
  Switch,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideInfo from "~icons/lucide/info";
import LucidePlugZap from "~icons/lucide/plug-zap";
import LucidePlus from "~icons/lucide/plus";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideX from "~icons/lucide/x";
import SecretField, { type SecretEdit } from "../SecretField.vue";
import SettingsAction from "../SettingsAction.vue";
import SettingsSection from "../SettingsSection.vue";
import { secretValue } from "../secretEdit";
import ConfigHistory from "./ConfigHistory.vue";
import {
  syncSummary,
  type Registry,
  type SourceSummary,
} from "./crmDashboards";

interface StatusRow {
  status: string;
  category: string;
  company: string;
}

interface RemoteField {
  fieldname: string;
  label: string | null;
  fieldtype: string;
  options: string | null;
}

/** helpdesk.api.crm_dashboard_settings.get_source */
interface SourceData extends SourceSummary {
  source_name: string;
  api_secret: { set: boolean; masked: string };
  status_map: StatusRow[];
  statuses: {
    status: string;
    company: string;
    category: string;
    leads: number;
  }[];
  modified: string;
  [field: string]: unknown;
}

const props = defineProps<{
  name: string | null;
  registry: Registry;
  reportingCurrency: string | null;
  crmConnection: { enabled: boolean; site_url: string | null };
}>();
const emit = defineEmits<{ back: []; saved: [name: string] }>();

const API = "helpdesk.api.crm_dashboard_settings";
const POLL_MS = 5000;
const PLAIN = [
  "source_name",
  "company_label",
  "use_crm_connection",
  "site_url",
  "api_key",
  "lead_doctype",
  "currency",
  "exchange_rate",
  "sync_every",
];
const SYNC_EVERY = [
  { label: __("15 minutes"), value: "15 minutes" },
  { label: __("Hour"), value: "Hourly" },
  { label: __("6 hours"), value: "Every 6 hours" },
  { label: __("Day"), value: "Daily" },
];

function blank(): Record<string, any> {
  const form: Record<string, any> = {
    source_name: "",
    enabled: true,
    company_label: "",
    use_crm_connection: !!props.crmConnection.site_url,
    site_url: "",
    api_key: "",
    lead_doctype: "Lead",
    currency: props.reportingCurrency || "",
    exchange_rate: 1,
    sync_every: "Hourly",
    status_map: [] as StatusRow[],
  };
  for (const target of Object.keys(props.registry.mapped_fields))
    form[target] = "";
  Object.assign(form, {
    owner_field: "lead_owner",
    status_field: "status",
    source_field: "source",
    created_field: "creation",
  });
  return form;
}

const form = reactive(blank());
const saved = ref(JSON.stringify(form));
const secret = ref<SecretEdit>({ mode: "keep", value: "" });

const source = createResource<SourceData>({
  url: `${API}.get_source`,
  makeParams: () => ({ name: props.name }),
  auto: !!props.name,
  onSuccess: fill,
});

function fill(data: SourceData) {
  const next = blank();
  for (const key of [...PLAIN, ...Object.keys(props.registry.mapped_fields)])
    next[key] = data[key] ?? next[key];
  next.enabled = !!data.enabled;
  next.use_crm_connection = !!data.use_crm_connection;
  next.status_map = data.status_map.map((row) => ({ ...row }));
  Object.assign(form, next);
  saved.value = JSON.stringify(form);
  secret.value = { mode: "keep", value: "" };
}

const dirty = computed(
  () => JSON.stringify(form) !== saved.value || secret.value.mode !== "keep"
);

// the site's own lead fields, for the mapping pickers
const remoteFields = createResource<{
  ok: boolean;
  fields: RemoteField[];
  message: string;
}>({
  url: `${API}.get_remote_fields`,
  makeParams: () => ({ name: props.name }),
  auto: !!props.name,
});
const fieldOptions = computed(() =>
  remoteFields.data?.ok && remoteFields.data.fields.length
    ? remoteFields.data.fields
    : null
);
const mappingNote = computed(() => {
  if (!props.name)
    return __("Save the connection first; then pick from its own lead fields.");
  if (remoteFields.loading && !remoteFields.data) return "";
  if (!fieldOptions.value)
    return __(
      "Couldn't read its lead fields ({0}), so type their names.",
      remoteFields.data?.message ||
        errorText(remoteFields.error, __("no answer"))
    );
  return "";
});

function optionsFor(target: string, kind: string) {
  const types = props.registry.field_types[kind] || [];
  const fields = (fieldOptions.value || []).filter(
    (f) => types.includes(f.fieldtype) || f.fieldname === form[target]
  );
  const options = fields.map((f) => ({
    label: f.label ? `${__(f.label)} (${f.fieldname})` : f.fieldname,
    value: f.fieldname,
  }));
  return props.registry.required_fields.includes(target)
    ? options
    : [{ label: __("Not mapped"), value: "" }, ...options];
}

function example(kind: string) {
  return (
    { money: "opportunity_amount", date: "creation", status: "status" }[kind] ||
    "territory"
  );
}

const categoryOptions = computed(() =>
  props.registry.categories.map((c) => ({ label: __(c), value: c }))
);

/** Statuses on the copied leads, and in the status field's choices, with no row yet. */
const unmapped = computed(() => {
  const mapped = new Set(
    form.status_map.map((row: StatusRow) => row.status.trim())
  );
  const found = new Map<string, number>();
  for (const row of source.data?.statuses || []) {
    if (row.status)
      found.set(row.status, (found.get(row.status) || 0) + row.leads);
  }
  const statusField = fieldOptions.value?.find(
    (f) => f.fieldname === form.status_field
  );
  if (statusField?.fieldtype === "Select") {
    for (const option of (statusField.options || "").split("\n")) {
      if (option.trim() && !found.has(option.trim()))
        found.set(option.trim(), 0);
    }
  }
  return [...found.entries()]
    .filter(([status]) => !mapped.has(status))
    .map(([status, leads]) => ({ status, leads }));
});

function addStatus(status: string) {
  form.status_map.push({ status, category: "", company: "" });
}

const saving = ref(false);
async function save() {
  if (saving.value) return;
  saving.value = true;
  try {
    const values: Record<string, unknown> = {
      ...Object.fromEntries(
        [...PLAIN, ...Object.keys(props.registry.mapped_fields)].map((k) => [
          k,
          form[k],
        ])
      ),
      enabled: form.enabled ? 1 : 0,
      use_crm_connection: form.use_crm_connection ? 1 : 0,
      status_map: form.status_map,
    };
    const newSecret = secretValue(secret.value);
    if (newSecret !== undefined) values.api_secret = newSecret;
    const result = await call(`${API}.save_source`, {
      values,
      name: props.name,
    });
    if (result.warning) toast.info(result.warning);
    else
      toast.success(
        props.name ? __("Data source saved") : __("Data source created")
      );
    if (props.name) {
      source.setData(result.source);
      fill(result.source);
      remoteFields.reload();
    } else {
      emit("saved", result.source.name);
    }
  } catch (e) {
    toast.error(errorText(e, __("Couldn't save the data source. Try again.")));
  } finally {
    saving.value = false;
  }
}

// a new source's page becomes the saved one's: load it
watch(
  () => props.name,
  (name) => {
    if (!name) return;
    source.reload();
    remoteFields.reload();
  }
);

const syncing = ref(false);
async function syncNow(full: boolean) {
  syncing.value = true;
  try {
    await call(`${API}.sync_source_now`, { name: props.name, full });
    toast.success(full ? __("Reading every lead again") : __("Sync started"));
    source.data && (source.data.running = true);
    poll.resume();
  } catch (e) {
    toast.error(errorText(e, __("Couldn't start the sync. Try again.")));
  } finally {
    syncing.value = false;
  }
}

// while a sync runs, its outcome is shown as soon as it is known
const poll = useIntervalFn(
  async () => {
    if (!props.name || dirty.value) return;
    const data = await call(`${API}.get_source`, { name: props.name });
    source.setData(data);
    if (!data.running) poll.pause();
  },
  POLL_MS,
  { immediate: false }
);
watch(
  () => source.data?.running,
  (running) => (running ? poll.resume() : null),
  { immediate: true }
);

const deleteOpen = ref(false);
const deleting = ref(false);
async function remove() {
  deleting.value = true;
  try {
    await call(`${API}.delete_source`, { name: props.name });
    toast.success(__("Data source deleted"));
    deleteOpen.value = false;
    emit("back");
  } catch (e) {
    toast.error(errorText(e, __("Couldn't delete it. Try again.")));
  } finally {
    deleting.value = false;
  }
}

const confirmLeave = ref(false);
function back() {
  if (dirty.value) confirmLeave.value = true;
  else emit("back");
}
</script>
