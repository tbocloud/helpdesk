<template>
  <Dialog
    :open="open"
    :title="handover ? __('Edit credentials') : __('Add credentials')"
    size="3xl"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <form
      :id="formId"
      class="flex flex-col gap-4"
      novalidate
      @submit.prevent="submit"
    >
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <TextInput
          v-model="form.handed_over_by"
          :label="__('Handed over by (at the client)')"
          maxlength="140"
          required
        />
        <TextInput
          v-model="form.handed_over_on"
          type="date"
          :label="__('Handed over on')"
          required
        />
      </div>

      <fieldset class="flex flex-col gap-3">
        <legend class="mb-1 text-base-medium text-ink-gray-9">
          {{ __("Logins") }}
        </legend>
        <div
          v-for="(item, index) in form.items"
          :key="item.key"
          class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 p-3"
        >
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormControl
              v-model="item.platform"
              type="select"
              :label="__('Platform')"
              :options="platforms"
            />
            <TextInput
              v-model="item.account_url"
              :label="__('Account URL')"
              placeholder="https://"
            />
            <TextInput v-model="item.username" :label="__('Username')" />
            <TextInput
              v-model="item.password"
              type="password"
              autocomplete="new-password"
              :label="__('Password')"
              :placeholder="
                item.name ? __('Leave empty to keep the saved one') : ''
              "
            />
            <TextInput
              v-model="item.two_factor_contact"
              :label="__('Two-factor contact')"
              :placeholder="__('Phone or email that gets the login code')"
            />
            <TextInput v-model="item.notes" :label="__('Notes')" />
          </div>
          <div class="flex justify-end">
            <Button
              variant="ghost"
              theme="red"
              :label="__('Remove this login')"
              @click="form.items.splice(index, 1)"
            >
              <template #prefix>
                <LucideTrash2 class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
        </div>
        <div>
          <Button :label="__('Add a login')" @click="addItem()">
            <template #prefix>
              <LucidePlus class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
      </fieldset>

      <FormControl
        v-model="form.remarks"
        type="textarea"
        :rows="2"
        :label="__('Remarks')"
      />

      <div
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ errorMessage }}</span>
      </div>
    </form>

    <template #actions="{ close }">
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="close" />
        <Button
          variant="solid"
          type="submit"
          :form="formId"
          :label="__('Save')"
          :loading="saving"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, Dialog, FormControl, TextInput, call, toast } from "frappe-ui";
import { reactive, ref, useId, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
import type { CredentialHandover } from "../credentialsMeta";

const props = defineProps<{
  open: boolean;
  projectId: string;
  platforms: string[];
  /** a received handover to change; without it the dialog records a new one */
  handover?: CredentialHandover | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  saved: [];
}>();

const formId = `credentials-form-${useId()}`;
const errorMessage = ref("");
const saving = ref(false);

interface ItemForm {
  key: number;
  name?: string;
  platform: string;
  account_url: string;
  username: string;
  password: string;
  two_factor_contact: string;
  notes: string;
}

let keys = 0;
const form = reactive({
  handed_over_by: "",
  handed_over_on: "",
  remarks: "",
  items: [] as ItemForm[],
});

function addItem(item: Partial<ItemForm> = {}) {
  form.items.push({
    key: keys++,
    platform: props.platforms[0] ?? "Other",
    account_url: "",
    username: "",
    password: "",
    two_factor_contact: "",
    notes: "",
    ...item,
  });
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    errorMessage.value = "";
    const h = props.handover;
    Object.assign(form, {
      handed_over_by: h?.handed_over_by ?? "",
      handed_over_on:
        h?.handed_over_on ?? new Date().toISOString().slice(0, 10),
      remarks: h?.remarks ?? "",
      items: [],
    });
    for (const i of h?.items ?? [])
      addItem({
        name: i.name,
        platform: i.platform,
        account_url: i.account_url ?? "",
        username: i.username ?? "",
        two_factor_contact: i.two_factor_contact ?? "",
        notes: i.notes ?? "",
      });
    if (!form.items.length) addItem();
  },
  { immediate: true }
);

async function submit() {
  if (!form.handed_over_by.trim() || !form.handed_over_on) {
    errorMessage.value = __("Say who handed the details over, and when.");
    return;
  }
  if (!form.items.every((i) => i.username.trim() || i.password || i.name)) {
    errorMessage.value = __(
      "Every login needs a username or a password, or remove it."
    );
    return;
  }
  errorMessage.value = "";
  saving.value = true;
  try {
    await call("helpdesk.api.client_credentials.save_handover", {
      project: props.projectId,
      name: props.handover?.name,
      handed_over_by: form.handed_over_by.trim(),
      handed_over_on: form.handed_over_on,
      remarks: form.remarks,
      items: form.items.map(({ key, ...item }) => item),
    });
    toast.success(__("Credentials saved"));
    emit("update:open", false);
    emit("saved");
  } catch (e) {
    errorMessage.value = errorText(e, __("Couldn't save. Try again."));
  } finally {
    saving.value = false;
  }
}
</script>
