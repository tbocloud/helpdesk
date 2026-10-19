<template>
  <!-- the proposal libraries on the ERP site: written once, assembled into every proposal -->
  <SettingsSection
    :title="__('Module catalogue')"
    :description="
      __(
        'Each module\'s pre-written text, scope, deliverables, effort and price. Ticking a module on a proposal brings all of it, at no AI cost.'
      )
    "
  >
    <template v-if="canEdit" #actions>
      <Button :label="__('New module')" @click="editModule(null)">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <SettingsList
      :items="data?.modules"
      :label="__('Module catalogue')"
      :loading="library.loading && !data"
      :error="library.error"
      :empty-icon="LucideBlocks"
      :empty-title="__('No modules yet')"
      :empty-message="__('Add the modules you propose most.')"
      @retry="library.reload()"
    >
      <template #default="{ item }">
        <SettingsListItem
          :title="item.module_name"
          :subtitle="moduleSubtitle(item)"
          :muted="!item.enabled"
          @open="editModule(item)"
        />
      </template>
    </SettingsList>
  </SettingsSection>

  <SettingsSection
    :title="__('Section libraries')"
    :description="
      __(
        'The company overview, terms, warranty, AMC plans, payment terms, timelines, scope, roles, assumptions, out of scope, risks, architecture and workflows that proposals are built from.'
      )
    "
  >
    <template #actions>
      <FormControl
        v-model="kind"
        type="select"
        class="w-56"
        :aria-label="__('Library')"
        :options="
          (data?.libraries || []).map((l) => ({ label: __(l), value: l }))
        "
      />
      <Button v-if="canEdit" :label="__('New item')" @click="editItem(null)">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <p class="text-p-sm text-ink-gray-6">{{ kindHelp }}</p>
    <SettingsList
      :items="items"
      :label="__('Library items')"
      :loading="library.loading && !data"
      :error="library.error"
      :empty-icon="LucideLibrary"
      :empty-title="__('Nothing in this library yet')"
      :empty-message="__('Add the first item.')"
      @retry="library.reload()"
    >
      <template #default="{ item }">
        <SettingsListItem
          :title="item.title"
          :subtitle="itemSubtitle(item)"
          :muted="!item.enabled"
          @open="editItem(item)"
        />
      </template>
    </SettingsList>
  </SettingsSection>

  <SettingsSection
    :title="__('Proposal images')"
    :description="
      __(
        'Pictures tagged by section and solution type: a new proposal picks a fitting one by its tags. They are public files, so nothing confidential.'
      )
    "
  >
    <template v-if="canEdit" #actions>
      <Button :label="__('Upload image')" @click="editImage(null)">
        <template #prefix>
          <LucideUpload class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <p v-if="!data?.images?.length" class="text-p-sm text-ink-gray-6">
      {{ __("No images yet. Proposals look complete without them.") }}
    </p>
    <ul v-else class="grid grid-cols-2 gap-3 sm:grid-cols-4" role="list">
      <li v-for="img in data.images" :key="img.name">
        <button
          type="button"
          class="flex w-full flex-col gap-1 rounded-lg border border-outline-gray-2 p-2 text-left hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          :class="img.enabled ? '' : 'opacity-60'"
          @click="editImage(img)"
        >
          <img
            :src="img.url || ''"
            :alt="img.alt_text"
            class="h-24 w-full rounded object-cover"
          />
          <span class="truncate text-sm text-ink-gray-8">{{ img.title }}</span>
          <span class="truncate text-xs text-ink-gray-5">{{
            lines(img.sections).join(", ") || __("No section tags")
          }}</span>
        </button>
      </li>
    </ul>
  </SettingsSection>

  <!-- one dialog edits a module, a library item or an image's tags -->
  <Dialog v-model:open="dialog.open" :title="dialog.title" size="2xl">
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="saveRecord"
    >
      <template v-if="dialog.kind === 'module'">
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <FormControl
            v-model="record.module_name"
            :label="__('Module')"
            required
            maxlength="140"
            :disabled="!canEdit"
          />
          <FormControl
            v-model="record.fit"
            type="select"
            :label="__('Usually')"
            :options="
              (data?.fits || []).map((f) => ({ label: __(f), value: f }))
            "
            :disabled="!canEdit"
          />
          <FormControl
            v-model.number="record.effort_days"
            type="number"
            min="0"
            step="0.5"
            :label="__('Standard effort (days)')"
            :disabled="!canEdit"
          />
          <FormControl
            v-model.number="record.default_price"
            type="number"
            min="0"
            step="any"
            :label="__('Default price')"
            :description="
              __(
                'Used when the module has no Item priced on the segment\'s list.'
              )
            "
            :disabled="!canEdit"
          />
          <FormControl
            v-model="record.item"
            :label="__('Item (optional)')"
            :description="
              __('An ERPNext Item code; priced from the rate card.')
            "
            :disabled="!canEdit"
          />
          <FormControl
            v-model="record.image_tag"
            :label="__('Image tag (optional)')"
            :disabled="!canEdit"
          />
        </div>
        <FormControl
          v-for="field in moduleTexts"
          :key="field.key"
          v-model="record[field.key]"
          type="textarea"
          :rows="field.rows"
          :label="field.label"
          :description="field.help"
          :disabled="!canEdit"
        />
      </template>

      <template v-else-if="dialog.kind === 'item'">
        <FormControl
          v-model="record.title"
          :label="__('Title')"
          required
          maxlength="140"
          :disabled="!canEdit"
        />
        <FormControl
          v-model="record.body"
          type="textarea"
          :rows="6"
          :label="__('Text')"
          :description="kindHelp"
          :disabled="!canEdit"
        />
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <FormControl
            v-if="record.library === 'Scope of Work'"
            v-model="record.group"
            type="select"
            :label="__('Subsection')"
            :options="
              (data?.scope_groups || []).map((g) => ({
                label: __(g),
                value: g,
              }))
            "
            :disabled="!canEdit"
          />
          <FormControl
            v-if="record.library === 'Agreement Clause'"
            v-model="record.group"
            type="select"
            :label="__('Agreement section')"
            :options="
              (data?.clause_groups || []).map((g) => ({
                label: __(g),
                value: g,
              }))
            "
            :disabled="!canEdit"
          />
          <FormControl
            v-if="record.library === 'Timeline'"
            v-model.number="record.weeks"
            type="number"
            min="1"
            :label="__('Days')"
            :disabled="!canEdit"
          />
          <FormControl
            v-if="record.library === 'AMC Plan'"
            v-model.number="record.amount"
            type="number"
            min="0"
            step="any"
            :label="__('Yearly price')"
            :disabled="!canEdit"
          />
          <FormControl
            v-model="record.condition"
            type="select"
            :label="__('Only when')"
            :options="conditionOptions"
            :disabled="!canEdit"
          />
          <FormControl
            v-model.number="record.sort_order"
            type="number"
            :label="__('Order')"
            :disabled="!canEdit"
          />
        </div>
      </template>

      <template v-else>
        <div v-if="!record.name" class="flex flex-col gap-1.5">
          <label :for="fileId" class="text-xs text-ink-gray-5">{{
            __("Image (PNG, JPEG or WebP, up to 5 MB)")
          }}</label>
          <input
            :id="fileId"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            class="text-sm"
            @change="pickFile"
          />
        </div>
        <img
          v-else-if="record.url"
          :src="record.url"
          :alt="record.alt_text"
          class="max-h-48 w-full rounded-lg object-contain"
        />
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <FormControl
            v-model="record.title"
            :label="__('Title')"
            required
            maxlength="140"
            :disabled="!canEdit"
          />
          <FormControl
            v-model="record.alt_text"
            :label="__('Alt text')"
            required
            maxlength="140"
            :disabled="!canEdit"
          />
        </div>
        <FormControl
          v-model="record.sections"
          type="textarea"
          :rows="2"
          :label="__('Suits sections (one a line)')"
          :description="
            __('e.g. Cover, Company Overview, Modules & Features, Project Team')
          "
          :disabled="!canEdit"
        />
        <FormControl
          v-model="record.modules"
          type="textarea"
          :rows="2"
          :label="__('Modules it shows (one a line, optional)')"
          :disabled="!canEdit"
        />
      </template>

      <template v-if="dialog.kind !== 'image' || record.name">
        <FormControl
          v-model="record.solution_types"
          type="textarea"
          :rows="2"
          :label="__('Solution types (one a line; blank: all)')"
          :disabled="!canEdit"
        />
        <FormControl
          v-model="record.enabled"
          type="checkbox"
          :label="__('Enabled')"
          :disabled="!canEdit"
        />
      </template>
      <p v-if="formError" role="alert" class="text-p-sm text-danger">
        {{ formError }}
      </p>
    </form>
    <template #actions="{ close }">
      <div class="flex flex-wrap justify-end gap-2">
        <Button
          v-if="canEdit && dialog.kind === 'module' && record.name && ai"
          class="mr-auto"
          :label="__('Draft with AI')"
          :tooltip="__('Fills the text once; review it before you save.')"
          :loading="draft.loading"
          @click="draft.submit({ module: record.name })"
        >
          <template #prefix>
            <LucideSparkles class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-if="canEdit && record.name"
          variant="ghost"
          theme="red"
          :label="__('Delete')"
          :loading="busy"
          @click="removeRecord"
        />
        <Button :label="canEdit ? __('Cancel') : __('Close')" @click="close" />
        <Button
          v-if="canEdit"
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Save')"
          :loading="busy"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  createResource,
  Dialog,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId } from "vue";
import LucideBlocks from "~icons/lucide/blocks";
import LucideLibrary from "~icons/lucide/library";
import LucidePlus from "~icons/lucide/plus";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideUpload from "~icons/lucide/upload";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";
import SettingsSection from "../SettingsSection.vue";

type Row = Record<string, any>;
interface Library {
  can_edit: boolean;
  modules: Row[];
  items: Row[];
  images: Row[];
  libraries: string[];
  conditions: string[];
  fits: string[];
  scope_groups: string[];
  /** an Agreement Clause's section in the project agreement */
  clause_groups?: string[];
}

defineProps<{ ai?: boolean }>();

const formId = `proposal-library-${useId()}`;
const fileId = `proposal-library-file-${useId()}`;

const library = createResource({
  url: "helpdesk.api.proposals.get_proposal_library",
  auto: true,
});
const data = computed(() => library.data as Library | undefined);
const canEdit = computed(() => !!data.value?.can_edit);

const kind = ref("Company Overview");
const items = computed(() =>
  (data.value?.items ?? []).filter((i) => i.library === kind.value)
);

const HELP: Record<string, string> = {
  "Company Overview": __(
    "Each item is a subsection: its title, then its text."
  ),
  "Solution Component": __(
    "A row of the Proposed Solution's table: the component and what it does."
  ),
  "Scope of Work": __(
    "A line of the scope, in its subsection; modules add their own."
  ),
  Workflow: __("Steps joined by →, e.g. Lead → Quotation → Order."),
  Architecture: __(
    "A layer and what we use; “Detailed architecture” rows show only when asked."
  ),
  Deliverable: __("One deliverable a line item."),
  Phase: __("A phase of the implementation plan and its activities."),
  Timeline: __(
    "A timeline template: “Phase | days” a line, adding up to its days."
  ),
  Role: __(
    "A team role and its responsibilities; “Large project” roles show on big projects."
  ),
  "Investment Note": __("A note above the price, e.g. on taxes or licences."),
  "Payment Terms": __(
    "A payment template: “Milestone | 30” a line, adding up to 100."
  ),
  Warranty: __("The warranty text."),
  "AMC Plan": __("A plan: “Feature | value” a line, and its yearly price."),
  Assumption: __("An assumption; modules add their own."),
  "Out of Scope": __("What is not included; modules add their own."),
  Risk: __("A risk, and how we handle it in the text."),
  Terms: __("A term: its heading, then its text."),
  "Agreement Clause": __(
    "A clause of the project agreement: its heading, its text and the section it shows in."
  ),
};
const kindHelp = computed(() => HELP[kind.value] || "");

const conditionOptions = computed(() => [
  { label: __("Always"), value: "" },
  ...(data.value?.conditions ?? []).map((c) => ({ label: __(c), value: c })),
]);

const moduleTexts = [
  { key: "description", label: __("What it covers"), rows: 2, help: "" },
  {
    key: "features",
    label: __("Key features"),
    rows: 4,
    help: __("One a line."),
  },
  {
    key: "scope",
    label: __("Scope of work"),
    rows: 4,
    help: __("“Subsection | what we do”, one a line."),
  },
  {
    key: "deliverables",
    label: __("Deliverables"),
    rows: 2,
    help: __("One a line."),
  },
  {
    key: "assumptions",
    label: __("Assumptions"),
    rows: 2,
    help: __("One a line."),
  },
  {
    key: "out_of_scope",
    label: __("Out of scope"),
    rows: 2,
    help: __("One a line."),
  },
  {
    key: "workflow",
    label: __("Workflow"),
    rows: 2,
    help: __("“Title: Step → Step → Step”, one a line."),
  },
  // what the module adds to an SRS (TBO Smart's docs/client-documents.md §6)
  {
    key: "srs_requirements",
    label: __("SRS: functional requirements"),
    rows: 4,
    help: __(
      "“Requirement | How the client accepts it”, one a line. Each becomes a numbered FR and a UAT test."
    ),
  },
  {
    key: "srs_roles",
    label: __("SRS: user roles"),
    rows: 2,
    help: __("“Role | What they may do”, one a line."),
  },
  {
    key: "srs_screens",
    label: __("SRS: screens and fields"),
    rows: 2,
    help: __("“Screen: field, field”, one a line."),
  },
  {
    key: "srs_validations",
    label: __("SRS: validations"),
    rows: 2,
    help: __("One rule a line."),
  },
  {
    key: "srs_notifications",
    label: __("SRS: notifications"),
    rows: 2,
    help: __("Who is told what, and when; one a line."),
  },
];

function lines(value?: string | null) {
  return (value || "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

function moduleSubtitle(m: Row) {
  return [
    __("{0} days", String(m.effort_days || 0)),
    m.item || (m.default_price ? String(m.default_price) : __("no price yet")),
    lines(m.solution_types).join(", ") || __("all solution types"),
  ].join(" · ");
}

function itemSubtitle(i: Row) {
  return [i.group, i.condition, lines(i.solution_types).join(", ")]
    .filter(Boolean)
    .join(" · ");
}

// --- the dialog ---

const dialog = reactive({ open: false, kind: "module", title: "" });
const record = ref<Row>({});
const formError = ref("");
const busy = ref(false);
const upload = reactive({ filename: "", content: "" });

function open(kindName: string, title: string, row: Row) {
  record.value = { ...row, enabled: row.enabled ?? 1 };
  formError.value = "";
  Object.assign(upload, { filename: "", content: "" });
  Object.assign(dialog, { open: true, kind: kindName, title });
}

function editModule(row: Row | null) {
  open(
    "module",
    row ? row.module_name : __("New module"),
    row ?? { fit: "Configured" }
  );
}

function editItem(row: Row | null) {
  open(
    "item",
    row ? row.title : __("New {0}", __(kind.value)),
    row ?? { library: kind.value }
  );
}

function editImage(row: Row | null) {
  open("image", row ? row.title : __("Upload image"), row ?? {});
}

function pickFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) {
    formError.value = __(
      "The image is larger than 5 MB. Make it smaller and try again."
    );
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    upload.filename = file.name;
    upload.content = String(reader.result).split(",", 2)[1] || "";
    if (!record.value.title)
      record.value.title = file.name.replace(/\.[^.]+$/, "");
  };
  reader.readAsDataURL(file);
}

async function saveRecord() {
  if (busy.value) return;
  formError.value = "";
  busy.value = true;
  try {
    const { url: _url, ...values } = record.value;
    const fresh =
      dialog.kind === "image" && !record.value.name
        ? await call("helpdesk.api.proposals.upload_library_image", {
            filename: upload.filename,
            content: upload.content,
            data: values,
          })
        : await call("helpdesk.api.proposals.save_library_record", {
            kind: dialog.kind,
            data: values,
          });
    library.setData(fresh);
    dialog.open = false;
    toast.success(__("Saved"));
  } catch (e) {
    formError.value = errorText(e, __("Couldn't save it."));
  } finally {
    busy.value = false;
  }
}

async function removeRecord() {
  if (busy.value) return;
  busy.value = true;
  try {
    library.setData(
      await call("helpdesk.api.proposals.delete_library_record", {
        kind: dialog.kind,
        name: record.value.name,
      })
    );
    dialog.open = false;
    toast.success(__("Deleted"));
  } catch (e) {
    formError.value = errorText(e, __("Couldn't delete it."));
  } finally {
    busy.value = false;
  }
}

const draft = createResource({
  url: "helpdesk.api.proposals.draft_library_module",
  method: "POST",
  onSuccess(d: { draft: Row }) {
    record.value = { ...record.value, ...d.draft };
    toast.success(__("Drafted. Review it, then save."));
  },
  onError(e: unknown) {
    formError.value = errorText(e, __("Couldn't draft it."));
  },
});
</script>
