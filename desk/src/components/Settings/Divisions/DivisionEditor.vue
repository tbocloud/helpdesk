<template>
  <SettingsLayoutBase
    :title="isNew ? __('New division') : form.division_name || name || ''"
    :description="
      isNew
        ? __('A country or business division with its own people and records.')
        : __(
            'Profile, ERP site, people, teams and departments of this division.'
          )
    "
    :back-label="__('Back to divisions')"
    :dirty="dirty"
    :saving="saving"
    :save-label="isNew ? __('Create division') : undefined"
    :save-disabled="isNew ? !requiredSet : undefined"
    :loading="!isNew && division.loading && !division.data"
    :error="isNew ? null : division.error"
    @retry="division.reload()"
    @back="emit('back')"
    @save="save"
  >
    <template v-if="!isNew && canEditCentral" #header-actions>
      <Dropdown :options="moreOptions">
        <Button
          variant="ghost"
          :aria-label="__('More actions')"
          @click="isConfirmingDelete = false"
        >
          <template #icon>
            <LucideEllipsis class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </Dropdown>
    </template>
    <template #content>
      <div class="flex flex-col">
        <SettingsSection
          :title="__('Profile')"
          :description="
            canEditCentral
              ? undefined
              : __(
                  'Name, country, workspace, currency and ERP site are set by Super Admins.'
                )
          "
        >
          <div class="flex flex-col gap-5">
            <SettingRow :label="__('Division name')" v-slot="{ id }">
              <FormControl
                :id="id"
                v-model="form.division_name"
                class="w-full sm:w-64"
                :disabled="!canEditCentral"
                :placeholder="__('e.g. India')"
              />
            </SettingRow>
            <SettingRow
              :label="__('Division code')"
              :description="
                __('2 to 10 capital letters or digits. It can\'t change later.')
              "
              v-slot="{ id }"
            >
              <FormControl
                :id="id"
                v-model="form.division_code"
                class="w-full sm:w-64"
                :disabled="!isNew"
                :placeholder="__('e.g. IND')"
                @update:model-value="
                  form.division_code = ($event || '').toUpperCase()
                "
              />
            </SettingRow>
            <SettingRow :label="__('Country')" v-slot="{ id, labelledby }">
              <Link
                v-if="canEditCentral"
                :id="id"
                :labelledby="labelledby"
                v-model="form.country"
                doctype="Country"
                class="w-full sm:w-64"
              />
              <FormControl
                v-else
                :id="id"
                :model-value="form.country"
                class="w-full sm:w-64"
                disabled
              />
            </SettingRow>
            <SettingRow
              :label="__('Workspace URL')"
              :description="
                __(
                  'Where the division\'s people work, e.g. https://india.teambackoffice.com.'
                )
              "
              v-slot="{ id }"
            >
              <FormControl
                :id="id"
                v-model="form.workspace_url"
                class="w-full sm:w-64"
                type="url"
                :disabled="!canEditCentral"
                placeholder="https://"
              />
            </SettingRow>
            <SettingRow :label="__('Currency')" v-slot="{ id, labelledby }">
              <!-- Link searches Currency on mount, which division admins can't read -->
              <Link
                v-if="canEditCentral"
                :id="id"
                :labelledby="labelledby"
                v-model="form.currency"
                doctype="Currency"
                class="w-full sm:w-64"
              />
              <FormControl
                v-else
                :id="id"
                :model-value="form.currency"
                class="w-full sm:w-64"
                disabled
              />
            </SettingRow>
            <SettingRow :label="__('Time zone')" v-slot="{ id, labelledby }">
              <Autocomplete
                :id="id"
                :labelledby="labelledby"
                :model-value="form.time_zone"
                :options="timeZones"
                class="w-full sm:w-64"
                :placeholder="__('Select time zone')"
                @update:model-value="form.time_zone = $event?.value || ''"
              />
            </SettingRow>
            <SettingRow
              :label="__('Default language')"
              v-slot="{ id, labelledby }"
            >
              <Link
                :id="id"
                :labelledby="labelledby"
                v-model="form.language"
                doctype="Language"
                class="w-full sm:w-64"
              />
            </SettingRow>
            <SettingRow
              :label="__('Division administrator')"
              :description="__('Added to the people as Division Admin.')"
              v-slot="{ id, labelledby }"
            >
              <Link
                :id="id"
                :labelledby="labelledby"
                v-model="form.division_admin"
                doctype="User"
                class="w-full sm:w-64"
                :disabled="!canEditCentral"
              />
            </SettingRow>
            <SettingRow
              :label="__('Status')"
              :description="
                __(
                  'An inactive division\'s records are hidden from its people.'
                )
              "
              v-slot="{ id }"
            >
              <FormControl
                :id="id"
                v-model="form.status"
                type="select"
                class="w-full sm:w-64"
                :disabled="!canEditCentral"
                :options="[
                  { label: __('Active'), value: 'Active' },
                  { label: __('Inactive'), value: 'Inactive' },
                ]"
              />
            </SettingRow>
            <SettingRow
              :label="__('ERP site')"
              :description="
                __(
                  'The division\'s ERPNext site. Its leads, customers and quotations live there.'
                )
              "
              v-slot="{ id, labelledby }"
            >
              <div class="flex w-full flex-wrap items-center gap-2 sm:w-auto">
                <!-- Link searches HD CRM Source on mount, which only Super Admins may read -->
                <Link
                  v-if="canEditCentral"
                  :id="id"
                  :labelledby="labelledby"
                  v-model="form.crm_source"
                  doctype="HD CRM Source"
                  class="w-full sm:w-64"
                />
                <FormControl
                  v-else
                  :id="id"
                  :model-value="form.crm_source"
                  class="w-full sm:w-64"
                  disabled
                />
                <Button
                  v-if="canEditCentral"
                  :label="
                    form.crm_source ? __('Edit ERP site') : __('Add ERP site')
                  "
                  @click="emit('openSource', form.crm_source || null)"
                />
              </div>
            </SettingRow>
          </div>
        </SettingsSection>

        <template v-if="!isNew">
          <SettingsSection
            :title="__('People')"
            :description="
              __(
                'Members see this division\'s records; their role says what they do in it. Saving a Division Admin makes them a Sales Manager on the division\'s ERP site (every lead there); a Division Sales User becomes a Sales User there (only their own leads).'
              )
            "
          >
            <div class="flex flex-col gap-3">
              <div
                v-if="erpProblems.length"
                role="status"
                class="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-p-sm text-warning"
              >
                <LucideTriangleAlert
                  class="mt-0.5 size-4 shrink-0"
                  aria-hidden="true"
                />
                <div>
                  <p>
                    {{
                      __(
                        "Saved, but the ERP site couldn't be set for everyone:"
                      )
                    }}
                  </p>
                  <ul class="mt-1 list-disc pl-4">
                    <li v-for="problem in erpProblems" :key="problem">
                      {{ problem }}
                    </li>
                  </ul>
                </div>
              </div>
              <div class="flex flex-wrap items-end gap-2">
                <Link
                  v-model="newMember"
                  doctype="User"
                  class="w-full sm:w-64"
                  :placeholder="__('Add a person')"
                  :aria-label="__('Add a person')"
                />
                <FormControl
                  v-model="newRole"
                  type="select"
                  class="w-full sm:w-48"
                  :aria-label="__('Their role')"
                  :options="roleOptions"
                />
                <Button
                  :label="__('Add')"
                  :disabled="!newMember"
                  @click="addMember"
                />
              </div>
              <p v-if="!members.length" class="text-p-sm text-ink-gray-6">
                {{ __("Nobody is in this division yet.") }}
              </p>
              <ul
                v-else
                class="divide-y divide-outline-gray-1 overflow-hidden rounded-xl border border-outline-gray-2"
                :aria-label="__('People')"
              >
                <li
                  v-for="(member, i) in members"
                  :key="member.user"
                  class="flex flex-wrap items-center gap-3 px-3 py-2.5"
                >
                  <PersonAvatar :name="member.full_name" />
                  <div class="flex min-w-0 flex-1 flex-col">
                    <span class="truncate text-base text-ink-gray-9">{{
                      member.full_name
                    }}</span>
                    <span
                      class="truncate font-mono text-p-xs text-ink-gray-6"
                      >{{ member.user }}</span
                    >
                  </div>
                  <FormControl
                    v-model="member.role"
                    type="select"
                    class="w-44"
                    :aria-label="__('Role of {0}', member.full_name)"
                    :disabled="!roles.includes(member.role)"
                    :options="roleOptions"
                  />
                  <Button
                    variant="ghost"
                    :aria-label="__('Remove {0}', member.full_name)"
                    :disabled="!roles.includes(member.role)"
                    @click="members.splice(i, 1)"
                  >
                    <template #icon>
                      <LucideX class="size-4" aria-hidden="true" />
                    </template>
                  </Button>
                </li>
              </ul>
            </div>
          </SettingsSection>

          <SettingsSection
            v-for="unit in UNITS"
            :key="unit.key"
            :title="unit.title"
            :description="unit.description"
          >
            <div class="flex flex-col gap-3">
              <Link
                :model-value="''"
                :doctype="unit.doctype"
                class="w-full sm:w-64"
                :placeholder="unit.add"
                :aria-label="unit.add"
                @update:model-value="addUnit(unit.key, $event)"
              />
              <p
                v-if="!units[unit.key].length"
                class="text-p-sm text-ink-gray-6"
              >
                {{ unit.empty }}
              </p>
              <ul v-else class="flex flex-wrap gap-2" :aria-label="unit.title">
                <li
                  v-for="(entry, i) in units[unit.key]"
                  :key="entry"
                  class="flex items-center gap-1 rounded-lg border border-outline-gray-2 bg-surface-gray-1 py-1 pl-2.5 pr-1 text-sm text-ink-gray-8"
                >
                  {{ entry }}
                  <Button
                    variant="ghost"
                    size="sm"
                    :aria-label="__('Remove {0}', entry)"
                    @click="units[unit.key].splice(i, 1)"
                  >
                    <template #icon>
                      <LucideX class="size-3.5" aria-hidden="true" />
                    </template>
                  </Button>
                </li>
              </ul>
            </div>
          </SettingsSection>
        </template>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import PersonAvatar from "@/components/PersonAvatar.vue";
import { DIVISIONS_API } from "@/pages/divisions/divisions";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { ConfirmDelete } from "@/utils";
import {
  Button,
  call,
  createResource,
  Dropdown,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideX from "~icons/lucide/x";
import SettingRow from "../SettingRow.vue";
import SettingsSection from "../SettingsSection.vue";

interface Member {
  user: string;
  full_name: string;
  role: string;
}
type UnitKey = "teams" | "departments";

const props = defineProps<{ name: string | null }>();
const emit = defineEmits<{
  back: [];
  created: [name: string];
  openSource: [name: string | null];
}>();

const auth = useAuthStore();
const isNew = computed(() => props.name === null);

const FIELDS = [
  "division_name",
  "division_code",
  "status",
  "country",
  "workspace_url",
  "currency",
  "time_zone",
  "language",
  "division_admin",
  "crm_source",
] as const;
type Profile = Record<(typeof FIELDS)[number], string>;

const blank = (): Profile =>
  Object.fromEntries(
    FIELDS.map((f) => [f, f === "status" ? "Active" : ""])
  ) as Profile;

const form = reactive<Profile>(blank());
const saved = ref<Profile>(blank());
const members = ref<Member[]>([]);
const savedMembers = ref("[]");
const units = reactive<Record<UnitKey, string[]>>({
  teams: [],
  departments: [],
});
const savedUnits = ref("{}");
const roles = ref<string[]>([]);
const canEditCentral = ref(true);
// people the division's ERP site couldn't be given their sales role, from the last save
const erpProblems = ref<string[]>([]);

const division = createResource({
  url: `${DIVISIONS_API}.get_division`,
  makeParams: () => ({ name: props.name }),
  onSuccess(data: any) {
    const profile = { ...blank() };
    for (const f of FIELDS) profile[f] = data.division[f] || "";
    Object.assign(form, profile);
    saved.value = profile;
    members.value = data.members.map((m: Member) => ({ ...m }));
    savedMembers.value = JSON.stringify(data.members);
    units.teams = [...data.teams];
    units.departments = [...data.departments];
    savedUnits.value = JSON.stringify(units);
    roles.value = data.roles;
    canEditCentral.value = data.can_edit_central;
  },
});

const options = createResource({
  url: `${DIVISIONS_API}.get_options`,
  auto: true,
  onSuccess(data: { roles: string[] }) {
    if (isNew.value) roles.value = data.roles;
  },
});
const timeZones = computed(() =>
  (options.data?.time_zones || []).map((tz: string) => ({
    label: tz,
    value: tz,
  }))
);

watch(
  () => props.name,
  (name) => {
    if (name) division.reload();
  },
  { immediate: true }
);

const roleOptions = computed(() =>
  (options.data?.roles || roles.value).map((r: string) => ({
    label: __(r),
    value: r,
    // a division's own admins can't give the Group Admin role
    disabled: !roles.value.includes(r),
  }))
);

const profileDirty = computed(() =>
  FIELDS.some((f) => (form[f] || "") !== (saved.value[f] || ""))
);
const membersDirty = computed(
  () =>
    JSON.stringify(members.value.map(({ user, role }) => ({ user, role }))) !==
    JSON.stringify(
      JSON.parse(savedMembers.value).map(({ user, role }: Member) => ({
        user,
        role,
      }))
    )
);
const unitsDirty = computed(() => JSON.stringify(units) !== savedUnits.value);
const dirty = computed(
  () => profileDirty.value || membersDirty.value || unitsDirty.value
);
const requiredSet = computed(
  () =>
    !!(
      form.division_name &&
      form.division_code &&
      form.country &&
      form.currency
    )
);

const newMember = ref("");
const newRole = ref("Employee");

function addMember() {
  if (members.value.some((m) => m.user === newMember.value)) {
    toast.error(__("{0} is already in this division", newMember.value));
    return;
  }
  members.value.push({
    user: newMember.value,
    full_name: newMember.value,
    role: newRole.value,
  });
  newMember.value = "";
}

const UNITS: {
  key: UnitKey;
  doctype: string;
  title: string;
  description: string;
  add: string;
  empty: string;
}[] = [
  {
    key: "teams",
    doctype: "HD Team",
    title: __("Teams"),
    description: __("The helpdesk teams that belong to this division."),
    add: __("Add a team"),
    empty: __("No teams in this division."),
  },
  {
    key: "departments",
    doctype: "HD Department",
    title: __("Departments"),
    description: __("The departments that belong to this division."),
    add: __("Add a department"),
    empty: __("No departments in this division."),
  },
];

function addUnit(key: UnitKey, value: string) {
  if (value && !units[key].includes(value)) units[key].push(value);
}

const saving = ref(false);

async function save() {
  saving.value = true;
  try {
    if (isNew.value) {
      const result = await call(`${DIVISIONS_API}.save_division`, {
        values: { ...form },
      });
      toast.success(__("Division created"));
      auth.reloadUser();
      emit("created", result.name);
      return;
    }
    const problems: string[] = [];
    if (profileDirty.value) {
      const result = await call(`${DIVISIONS_API}.save_division`, {
        name: props.name,
        values: { ...form },
      });
      problems.push(...(result.erp_problems || []));
    }
    if (membersDirty.value) {
      const result = await call(`${DIVISIONS_API}.set_members`, {
        division: props.name,
        members: members.value.map(({ user, role }) => ({ user, role })),
      });
      problems.push(...(result.erp_problems || []));
    }
    erpProblems.value = problems;
    if (unitsDirty.value)
      await call(`${DIVISIONS_API}.set_units`, {
        division: props.name,
        teams: units.teams,
        departments: units.departments,
      });
    toast.success(__("Division saved"));
    auth.reloadUser();
    division.reload();
  } catch (error: any) {
    toast.error(error?.messages?.[0] || __("Couldn't save the division"));
  } finally {
    saving.value = false;
  }
}

/** A site just added from this division: picked here, saved with the division. */
function useSource(name: string) {
  form.crm_source = name;
}
defineExpose({ useSource });

const isConfirmingDelete = ref(false);
// Frappe refuses while a project, team or department is still in the division
const moreOptions = computed(() =>
  ConfirmDelete({ isConfirmingDelete, onConfirmDelete: remove })
);

async function remove() {
  try {
    await call(`${DIVISIONS_API}.delete_division`, { name: props.name });
    toast.success(__("Division deleted"));
    auth.reloadUser();
    emit("back");
  } catch (error: any) {
    isConfirmingDelete.value = false;
    toast.error(error?.messages?.[0] || __("Couldn't delete the division"));
  }
}
</script>
