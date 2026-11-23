<template>
  <!-- the payment terms templates proposals pick from: milestones adding up to 100%, kept in
       the ERP site's Payment Terms library (docs/proposals.md) -->
  <SettingsSection
    :title="__('Payment terms templates')"
    :description="
      __(
        'The milestones a proposal can be paid in. Each template shows in the proposal’s Payment terms list; a proposal can still set its own.'
      )
    "
  >
    <template #actions>
      <Button v-if="canEdit" :label="__('New template')" @click="edit(null)">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </template>
    <SettingsList
      :items="templates"
      :label="__('Payment terms templates')"
      :loading="loading"
      :error="error"
      :empty-icon="LucideWallet"
      :empty-title="__('No payment terms templates yet')"
      :empty-message="
        canEdit
          ? __('Add one, e.g. 50% on signing and 50% on go-live.')
          : __('Someone who may edit the ERP site’s library can add them.')
      "
      @retry="emit('retry')"
    >
      <template #default="{ item }">
        <SettingsListItem
          :title="item.title"
          :subtitle="subtitle(item)"
          :muted="!item.enabled"
          @open="edit(item)"
        >
          <template #meta>
            <!-- the split at a glance; the subtitle says it in words -->
            <span
              class="hidden h-2 w-28 shrink-0 gap-px overflow-hidden rounded-full sm:flex"
              aria-hidden="true"
            >
              <span
                v-for="(m, k) in item.milestones"
                :key="k"
                class="h-full bg-brand"
                :style="{
                  width: `${m.share}%`,
                  opacity: 1 - (k % 4) * 0.2,
                }"
              />
            </span>
          </template>
        </SettingsListItem>
      </template>
    </SettingsList>
  </SettingsSection>

  <Dialog v-model:open="dialog.open" :title="dialog.title" size="lg">
    <form :id="formId" class="flex flex-col gap-4" @submit.prevent="save">
      <fieldset class="flex flex-col gap-4" :disabled="!canEdit">
        <FormControl
          v-model="form.title"
          type="text"
          :label="__('Name')"
          :placeholder="__('e.g. 40 / 40 / 20')"
          :description="__('As it shows in the proposal’s Payment terms list.')"
          maxlength="140"
          required
        />
        <div class="flex flex-col gap-1.5">
          <span class="text-xs text-ink-gray-5">{{ __("Milestones") }}</span>
          <PaymentMilestonesEditor
            v-model="form.milestones"
            :disabled="!canEdit"
          />
        </div>
        <FormControl
          v-model="form.solution_types"
          type="textarea"
          :rows="2"
          :label="__('Solution types (one a line; blank: all)')"
        />
        <div class="flex flex-wrap items-end gap-4">
          <FormControl
            v-model.number="form.sort_order"
            class="w-28"
            type="number"
            min="0"
            :label="__('Order')"
          />
          <FormControl
            v-model="form.enabled"
            type="checkbox"
            :label="__('Enabled')"
          />
        </div>
      </fieldset>
      <p v-if="formError" role="alert" class="text-p-sm text-danger">
        {{ formError }}
      </p>
    </form>
    <template #actions>
      <div class="flex flex-wrap items-center gap-2">
        <Button
          v-if="canEdit && form.name"
          theme="red"
          variant="ghost"
          :label="confirmDelete ? __('Delete it') : __('Delete')"
          :loading="busy && confirmDelete"
          @click="remove"
        />
        <span
          v-if="confirmDelete"
          class="text-p-sm text-ink-gray-6"
          role="status"
          >{{ __("Proposals already made keep their terms.") }}</span
        >
        <div class="ml-auto flex gap-2">
          <Button
            :label="canEdit ? __('Cancel') : __('Close')"
            @click="dialog.open = false"
          />
          <Button
            v-if="canEdit"
            variant="solid"
            type="submit"
            :form="formId"
            :label="__('Save')"
            :loading="busy && !confirmDelete"
            :disabled="!ready"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import PaymentMilestonesEditor from "@/pages/leads/PaymentMilestonesEditor.vue";
import {
  addsUp,
  milestonesBody,
  parseMilestones,
  type PaymentMilestone,
} from "@/pages/leads/proposals";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, Dialog, FormControl, toast } from "frappe-ui";
import { computed, reactive, ref, useId } from "vue";
import LucidePlus from "~icons/lucide/plus";
import LucideWallet from "~icons/lucide/wallet";
import SettingsList from "../SettingsList.vue";
import SettingsListItem from "../SettingsListItem.vue";
import SettingsSection from "../SettingsSection.vue";

type Row = Record<string, any>;

const LIBRARY = "Payment Terms";

const props = defineProps<{
  /** the library's items (every library); the Payment Terms ones are shown */
  items: Row[];
  canEdit: boolean;
  loading?: boolean;
  error?: unknown;
}>();
const emit = defineEmits<{
  /** the library as the ERP site has it after a save or delete */
  (e: "saved", library: unknown): void;
  (e: "retry"): void;
}>();

const formId = `payment-terms-${useId()}`;

const templates = computed(() =>
  props.items
    .filter((i) => i.library === LIBRARY)
    .map((i) => ({ ...i, milestones: parseMilestones(i.body) }))
);

function lines(value?: string | null) {
  return (value || "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

function subtitle(item: Row & { milestones: PaymentMilestone[] }) {
  return [
    item.milestones.length
      ? item.milestones.map((m) => `${m.share}% ${m.label}`).join(" · ")
      : __("No milestones"),
    lines(item.solution_types).join(", "),
  ]
    .filter(Boolean)
    .join(" — ");
}

const dialog = reactive({ open: false, title: "" });
const form = ref<Row & { milestones: PaymentMilestone[] }>({ milestones: [] });
const formError = ref("");
const busy = ref(false);
const confirmDelete = ref(false);

const ready = computed(
  () =>
    !!String(form.value.title || "").trim() &&
    form.value.milestones.length > 0 &&
    form.value.milestones.every((m) => m.label.trim() && m.share > 0) &&
    addsUp(form.value.milestones)
);

function edit(row: Row | null) {
  form.value = row
    ? { ...row, milestones: parseMilestones(row.body) }
    : {
        library: LIBRARY,
        title: "",
        enabled: 1,
        sort_order: templates.value.length + 1,
        milestones: [
          { label: __("Advance on signing"), share: 50 },
          { label: __("On go-live"), share: 50 },
        ],
      };
  dialog.title = row ? row.title : __("New payment terms template");
  formError.value = "";
  confirmDelete.value = false;
  dialog.open = true;
}

async function save() {
  if (busy.value || !ready.value) return;
  busy.value = true;
  formError.value = "";
  try {
    const { milestones, url: _url, ...values } = form.value;
    const fresh = await call("helpdesk.api.proposals.save_library_record", {
      kind: "item",
      data: {
        ...values,
        library: LIBRARY,
        title: String(values.title).trim(),
        body: milestonesBody(milestones),
      },
    });
    emit("saved", fresh);
    dialog.open = false;
    toast.success(__("Saved"));
  } catch (e) {
    formError.value = errorText(e, __("Couldn't save it."));
  } finally {
    busy.value = false;
  }
}

/** Asks once ("Delete it"), then deletes. */
async function remove() {
  if (!confirmDelete.value) {
    confirmDelete.value = true;
    return;
  }
  if (busy.value) return;
  busy.value = true;
  formError.value = "";
  try {
    emit(
      "saved",
      await call("helpdesk.api.proposals.delete_library_record", {
        kind: "item",
        name: form.value.name,
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
</script>
