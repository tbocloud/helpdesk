<template>
  <SettingsLayoutBase
    :title="
      template
        ? form.template_name || template.name
        : __('New proposal template')
    "
    :back-label="__('Back to rates and proposals')"
    :dirty="dirty"
    :save-label="template ? __('Save changes') : __('Create template')"
    :save-disabled="!!template && !dirty"
    :saving="saving"
    @back="back"
    @save="save"
  >
    <template #header-actions>
      <Switch v-model="form.enabled" size="sm" :label="__('Enabled')" />
    </template>
    <template #content>
      <div class="flex flex-col gap-6">
        <SettingsSection :title="__('Details')">
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormControl
              v-model="form.template_name"
              :label="__('Name')"
              :placeholder="__('e.g. ERPNext Implementation')"
              maxlength="140"
              required
            />
            <FormControl
              v-model="form.solution_type"
              :label="__('Solution type')"
              :description="
                __('A new proposal is titled “<solution type> for <client>”.')
              "
              maxlength="140"
            />
          </div>
          <FormControl
            v-model="form.description"
            type="textarea"
            :rows="2"
            :label="__('Description')"
            :description="__('Shown when someone picks a template.')"
          />
          <FormControl
            v-model="form.page_guide"
            type="select"
            :label="__('Length guide')"
            :options="pageGuides"
            :description="
              __('Shown in the builder beside the proposal\'s page count.')
            "
          />
        </SettingsSection>
        <SettingsSection
          :title="__('Scoping questions')"
          :description="
            __('What the scoping form asks for this kind of proposal.')
          "
        >
          <div class="flex flex-wrap gap-2">
            <label
              v-for="q in QUESTIONS"
              :key="q"
              class="flex min-h-[36px] cursor-pointer items-center gap-2 rounded-md border px-3"
              :class="
                form.questions.includes(q)
                  ? 'border-brand bg-brand-soft text-brand-ink'
                  : 'border-outline-gray-2 text-ink-gray-7'
              "
            >
              <input
                v-model="form.questions"
                type="checkbox"
                :value="q"
                class="size-4 rounded border-outline-gray-4 focus-visible:ring-2 focus-visible:ring-highlight"
              />
              <span class="text-sm">{{ QUESTION_LABELS[q] }}</span>
            </label>
          </div>
        </SettingsSection>
        <SettingsSection
          :title="__('Default modules')"
          :description="
            __('Ticked on a new proposal; presales adds or removes them.')
          "
        >
          <div class="flex flex-wrap gap-2">
            <label
              v-for="m in catalogue"
              :key="m"
              class="flex min-h-[36px] cursor-pointer items-center gap-2 rounded-md border px-3"
              :class="
                form.default_modules.includes(m)
                  ? 'border-brand bg-brand-soft text-brand-ink'
                  : 'border-outline-gray-2 text-ink-gray-7'
              "
            >
              <input
                v-model="form.default_modules"
                type="checkbox"
                :value="m"
                class="size-4 rounded border-outline-gray-4 focus-visible:ring-2 focus-visible:ring-highlight"
              />
              <span class="text-sm">{{ m }}</span>
            </label>
          </div>
        </SettingsSection>
        <SettingsSection
          :title="__('Default packages')"
          :description="
            __(
              'The quotation packages that usually price this kind of proposal.'
            )
          "
        >
          <p v-if="!packages.length" class="text-p-sm text-ink-gray-6">
            {{ __("No quotation packages on the ERP site yet.") }}
          </p>
          <div v-else class="flex flex-wrap gap-2">
            <label
              v-for="p in packages"
              :key="p"
              class="flex min-h-[36px] cursor-pointer items-center gap-2 rounded-md border px-3"
              :class="
                form.packages.includes(p)
                  ? 'border-brand bg-brand-soft text-brand-ink'
                  : 'border-outline-gray-2 text-ink-gray-7'
              "
            >
              <input
                v-model="form.packages"
                type="checkbox"
                :value="p"
                class="size-4 rounded border-outline-gray-4 focus-visible:ring-2 focus-visible:ring-highlight"
              />
              <span class="text-sm">{{ p }}</span>
            </label>
          </div>
        </SettingsSection>
        <SettingsSection
          :title="__('Sections')"
          :description="
            __(
              'Every new proposal starts with all of them on; the guidance is the AI\'s brief and the placeholder.'
            )
          "
        >
          <ProposalBlocks
            v-model:sections="form.sections"
            editable
            with-guidance
            :guidance="{}"
            :section-types="sectionTypes"
          />
        </SettingsSection>
        <p v-if="error" role="alert" class="text-p-sm text-danger">
          {{ error }}
        </p>
      </div>
    </template>
  </SettingsLayoutBase>
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
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import ProposalBlocks from "@/pages/leads/ProposalBlocks.vue";
import {
  QUESTION_LABELS,
  QUESTIONS,
  type ProposalOptions,
  type ProposalTemplate,
  type SectionType,
  type TemplateSection,
} from "@/pages/leads/proposals";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { call, FormControl, Switch, toast } from "frappe-ui";
import { computed, reactive, ref } from "vue";
import SettingsSection from "../SettingsSection.vue";

const props = defineProps<{
  template: ProposalTemplate | null;
  packages: string[];
  sectionTypes: SectionType[];
  /** the catalogue's module names */
  catalogue: string[];
  /** the master sections with their default headings, for a new template */
  defaultHeadings: Record<string, string>;
}>();

const pageGuides = [
  "Small project (5–8 pages)",
  "ERP (10–15 pages)",
  "ERP + mobile (15–25 pages)",
  "Enterprise (20–35 pages)",
].map((g) => ({ label: __(g), value: g }));
const emit = defineEmits<{ back: []; saved: [options: ProposalOptions] }>();

const t = props.template;
const form = reactive({
  template_name: t?.template_name || "",
  solution_type: t?.solution_type || "",
  description: t?.description || "",
  enabled: t ? !!t.enabled : true,
  packages: [...(t?.packages ?? [])],
  page_guide: t?.page_guide || "ERP (10–15 pages)",
  questions: [...(t?.questions?.length ? t.questions : QUESTIONS)] as string[],
  default_modules: [...(t?.default_modules ?? [])],
  sections: (
    t?.sections ??
    Object.entries(props.defaultHeadings).map(([section_type, heading]) => ({
      section_type,
      heading,
      enabled: 1,
    }))
  ).map((s) => ({ ...s })) as TemplateSection[],
});
const snapshot = () => JSON.stringify(form);
const saved = ref(snapshot());
const dirty = computed(() => snapshot() !== saved.value);
const saving = ref(false);
const error = ref("");
const confirmLeave = ref(false);

function back() {
  if (dirty.value) confirmLeave.value = true;
  else emit("back");
}

async function save() {
  if (!form.template_name.trim() || !form.sections.length) {
    error.value = __("Give the template a name and at least one section.");
    return;
  }
  error.value = "";
  saving.value = true;
  try {
    const options = await call("helpdesk.api.proposals.save_template", {
      data: { name: t?.name || null, ...form, enabled: form.enabled ? 1 : 0 },
    });
    saved.value = snapshot();
    toast.success(__("Template saved"));
    emit("saved", options);
  } catch (e) {
    error.value = errorText(e, __("Couldn't save the template."));
  } finally {
    saving.value = false;
  }
}
</script>
