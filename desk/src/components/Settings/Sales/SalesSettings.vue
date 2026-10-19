<template>
  <ProposalTemplateEditor
    v-if="editing !== null"
    :template="editing === 'new' ? null : editing"
    :packages="options?.packages || []"
    :section-types="options?.section_types || []"
    @back="editing = null"
    @saved="onTemplateSaved"
  />
  <SettingsLayoutBase
    v-else
    :title="__('Rates and proposals')"
    :description="
      __(
        'Each lead segment\'s price list and discount band, the templates new proposals start from and their letter head. They live on the ERP site.'
      )
    "
    :dirty="dirty"
    :saving="saving"
    :loading="card.loading && !cardData"
    :error="card.error"
    @retry="card.reload()"
    @save="save"
  >
    <template #content>
      <div v-if="cardData" class="flex flex-col">
        <p
          v-if="!canEdit"
          class="mb-6 rounded-md bg-surface-gray-1 px-3 py-2 text-p-sm text-ink-gray-7"
        >
          {{
            __(
              "You can see these. Only the people who edit quotation presets and prices on the ERP site can change them."
            )
          }}
        </p>
        <SettingsSection
          :title="__('Segment rate card')"
          :description="
            __(
              'Anyone may give up to the band on a lead in that segment without approval; above it the quotation approvals apply. Blank price list: {0}.',
              cardData.default_price_list || __('the selling price list')
            )
          "
        >
          <div class="overflow-hidden rounded-lg border border-outline-gray-2">
            <div
              aria-hidden="true"
              class="hidden grid-cols-[8rem_1fr_9rem] gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-xs text-ink-gray-6 sm:grid"
            >
              <span>{{ __("Segment") }}</span>
              <span>{{ __("Price list") }}</span>
              <span class="text-right">{{ __("Discount band %") }}</span>
            </div>
            <div
              v-for="row in rows"
              :key="row.segment"
              class="grid grid-cols-2 items-center gap-3 border-b border-outline-gray-1 px-3 py-2 last:border-b-0 sm:grid-cols-[8rem_1fr_9rem]"
            >
              <span
                class="col-span-2 text-base-medium text-ink-gray-8 sm:col-span-1"
                >{{ __(row.segment) }}</span
              >
              <FormControl
                v-model="row.price_list"
                type="select"
                :aria-label="__('{0} price list', row.segment)"
                :options="priceListOptions"
                :disabled="!canEdit"
              />
              <FormControl
                v-model.number="row.max_discount"
                type="number"
                min="0"
                max="100"
                step="any"
                class="text-right"
                :aria-label="__('{0} discount band %', row.segment)"
                :disabled="!canEdit"
              />
            </div>
          </div>
        </SettingsSection>

        <SettingsSection
          :title="__('Service rates')"
          :description="
            __(
              'The rate of each service on a price list. A segment without a list of its own uses the selling list\'s rates.'
            )
          "
        >
          <TabButtons
            :model-value="rateList"
            :aria-label="__('Rates of')"
            :options="rateListOptions"
            @update:model-value="rateList = $event"
          />
          <p v-if="!cardData.services.length" class="text-p-sm text-ink-gray-6">
            {{ __("No sales items on the ERP site yet.") }}
          </p>
          <ul
            v-else
            role="list"
            class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2"
          >
            <li
              v-for="s in cardData.services"
              :key="s.item_code"
              class="flex flex-wrap items-center gap-3 px-3 py-2"
            >
              <div class="flex min-w-0 flex-1 flex-col">
                <span class="truncate text-base text-ink-gray-8">{{
                  s.item_name
                }}</span>
                <span class="text-xs text-ink-gray-5">{{ s.item_group }}</span>
              </div>
              <FormControl
                class="w-36"
                type="number"
                min="0"
                step="any"
                :aria-label="__('{0} rate', s.item_name)"
                :placeholder="rateList ? String(s.rate) : ''"
                :model-value="rateValue(s)"
                :disabled="!canEdit"
                @update:model-value="setRate(s.item_code, $event)"
              />
            </li>
          </ul>
        </SettingsSection>

        <SettingsSection
          v-if="options?.enabled"
          :title="__('Proposal letter head')"
          :description="
            __(
              'The header and footer on every proposal\'s page and PDF, unless a proposal picks another. They are the ERP site\'s Letter Heads.'
            )
          "
        >
          <p
            v-if="!options.letter_heads?.length"
            role="status"
            class="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-p-sm text-warning"
          >
            <LucideTriangleAlert
              class="mt-0.5 size-4 shrink-0"
              aria-hidden="true"
            />
            {{
              __(
                "The ERP site has no Letter Head yet, so proposals show only the company's logo. Add one there (Letter Head) and mark it default."
              )
            }}
          </p>
          <FormControl
            v-else
            v-model="letterHead"
            type="select"
            class="sm:max-w-sm"
            :label="__('Default letter head')"
            :options="letterHeadOptions"
            :disabled="!canEditTemplates"
          />
        </SettingsSection>

        <SettingsSection
          :title="__('Proposal templates')"
          :description="
            __(
              'A new proposal copies a template\'s blocks; editing a template never changes a proposal already made.'
            )
          "
        >
          <template v-if="canEditTemplates" #actions>
            <Button :label="__('New template')" @click="editing = 'new'">
              <template #prefix>
                <LucidePlus class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </template>
          <SettingsList
            :items="options?.templates"
            :label="__('Proposal templates')"
            :loading="proposalOptions.loading && !options"
            :error="proposalOptions.error"
            :empty-icon="LucideScrollText"
            :empty-title="
              options?.enabled === false
                ? __('Proposals are off on the ERP site')
                : __('No proposal templates yet')
            "
            :empty-message="
              options?.enabled === false
                ? __('Switch on Proposals in TBO Smart Settings there.')
                : __('Make one per kind of work you propose.')
            "
            @retry="proposalOptions.reload()"
          >
            <template #default="{ item }">
              <SettingsListItem
                :title="item.template_name"
                :subtitle="templateSubtitle(item)"
                :muted="!item.enabled"
                @open="canEditTemplates ? (editing = item) : undefined"
              >
                <template #badges>
                  <TaskyBadge v-if="!item.enabled" :label="__('Disabled')" />
                </template>
              </SettingsListItem>
            </template>
          </SettingsList>
        </SettingsSection>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup lang="ts">
import SettingsLayoutBase from "@/components/layouts/SettingsLayoutBase.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import {
  loadProposalOptions,
  proposalOptions,
  type ProposalOptions,
  type ProposalTemplate,
} from "@/pages/leads/proposals";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  createResource,
  FormControl,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucidePlus from "~icons/lucide/plus";
import LucideScrollText from "~icons/lucide/scroll-text";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";
import SettingsSection from "../SettingsSection.vue";
import ProposalTemplateEditor from "./ProposalTemplateEditor.vue";

interface CardRow {
  segment: string;
  price_list: string | null;
  max_discount: number;
}
interface Service {
  item_code: string;
  item_name: string;
  item_group?: string;
  rate: number;
  rates: Record<string, number | null>;
}
interface RateCard {
  segments: CardRow[];
  default_price_list?: string | null;
  price_lists: string[];
  services: Service[];
  can_edit: boolean;
}

const rows = ref<CardRow[]>([]);
const savedRows = ref("");
/** "<segment>|<item>" (blank segment: the selling list) → the new rate */
const rateEdits = ref<Record<string, number>>({});
const rateList = ref("");
const saving = ref(false);

const card = createResource({
  url: "helpdesk.api.proposals.get_rate_card",
  auto: true,
  onSuccess(d: RateCard) {
    rows.value = d.segments.map((r) => ({
      ...r,
      price_list: r.price_list || "",
    }));
    savedRows.value = JSON.stringify(rows.value);
    rateEdits.value = {};
  },
  onError() {},
});
const cardData = computed(() => card.data as RateCard | undefined);
const canEdit = computed(() => !!cardData.value?.can_edit);

loadProposalOptions();
const options = computed(
  () => proposalOptions.data as ProposalOptions | undefined
);
const canEditTemplates = computed(() => !!options.value?.can_edit_templates);

/** TBO Smart Settings → Proposal letter head; "": the Letter Head marked default */
const letterHead = ref("");
const savedLetterHead = computed(
  () => options.value?.proposal_letter_head || ""
);
watch(savedLetterHead, (v) => (letterHead.value = v), { immediate: true });
const letterHeadOptions = computed(() => {
  const marked = options.value?.letter_heads?.find((h) => h.is_default);
  return [
    {
      label: marked
        ? __("The one marked default ({0})", marked.name)
        : __("The one marked default"),
      value: "",
    },
    ...(options.value?.letter_heads ?? []).map((h) => ({
      label: h.name,
      value: h.name,
    })),
  ];
});
const letterHeadDirty = computed(
  () => canEditTemplates.value && letterHead.value !== savedLetterHead.value
);

const priceListOptions = computed(() => [
  { label: __("Selling price list"), value: "" },
  ...(cardData.value?.price_lists ?? []).map((p) => ({ label: p, value: p })),
]);
/** Only lists saved on the card have rates of their own to edit. */
const rateListOptions = computed(() => [
  {
    label: cardData.value?.default_price_list || __("Selling list"),
    value: "",
  },
  ...(cardData.value?.segments ?? [])
    .filter((r) => r.price_list)
    .map((r) => ({ label: __(r.segment), value: r.segment })),
]);

function rateValue(s: Service) {
  const key = `${rateList.value}|${s.item_code}`;
  if (key in rateEdits.value) return rateEdits.value[key];
  return rateList.value ? s.rates[rateList.value] ?? "" : s.rate;
}

function setRate(item: string, value: string | number) {
  rateEdits.value = {
    ...rateEdits.value,
    [`${rateList.value}|${item}`]: Number(value) || 0,
  };
}

const ratesDirty = computed(
  () =>
    canEdit.value &&
    (JSON.stringify(rows.value) !== savedRows.value ||
      Object.keys(rateEdits.value).length > 0)
);
const dirty = computed(() => ratesDirty.value || letterHeadDirty.value);

async function save() {
  if (saving.value || !dirty.value) return;
  saving.value = true;
  try {
    if (JSON.stringify(rows.value) !== savedRows.value) {
      await call("helpdesk.api.proposals.save_rate_card", {
        rows: rows.value.map((r) => ({
          segment: r.segment,
          price_list: r.price_list || null,
          max_discount: Number(r.max_discount) || 0,
        })),
      });
    }
    for (const [key, rate] of Object.entries(rateEdits.value)) {
      const [segment, item_code] = key.split("|");
      await call("helpdesk.api.proposals.set_segment_rate", {
        item_code,
        rate,
        segment: segment || null,
      });
    }
    if (letterHeadDirty.value) {
      proposalOptions.setData(
        await call("helpdesk.api.proposals.set_default_letter_head", {
          letter_head: letterHead.value || null,
        })
      );
    }
    toast.success(__("Saved"));
    card.reload();
  } catch (e) {
    toast.error(errorText(e, __("Couldn't save. Try again.")));
  } finally {
    saving.value = false;
  }
}

// --- templates ---

/** null: the page; "new": a new template; else that template, in the editor */
const editing = ref<ProposalTemplate | "new" | null>(null);

function templateSubtitle(t: ProposalTemplate) {
  const blocks = __("{0} blocks", String(t.sections.length));
  return t.solution_type ? `${t.solution_type} · ${blocks}` : blocks;
}

function onTemplateSaved(data: ProposalOptions) {
  proposalOptions.setData(data);
  editing.value = null;
}
</script>
