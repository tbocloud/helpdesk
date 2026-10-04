<template>
  <Dialog v-model:open="open" :options="{ size: 'lg' }">
    <template #body-title>
      <h3 class="text-xl-semibold text-ink-gray-9">
        {{ occasion ? __("Edit occasion") : __("Add occasion") }}
      </h3>
    </template>
    <template #body-content>
      <form
        id="occasion-form"
        class="flex flex-col gap-4"
        novalidate
        @submit.prevent="save"
      >
        <FormControl
          v-model="form.occasion_name"
          :label="__('Occasion') + ' *'"
          :placeholder="__('e.g. Diwali')"
          required
        />
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormControl
            v-model="form.occasion_date"
            type="date"
            :label="__('Date') + ' *'"
          />
          <FormControl
            v-model="form.region"
            type="select"
            :label="__('Region')"
            :options="REGIONS"
          />
        </div>
        <div class="flex flex-col gap-1">
          <FormControl
            v-model="form.repeats_yearly"
            type="checkbox"
            :label="__('Same date every year')"
          />
          <p class="ps-6 text-p-sm text-ink-gray-5">
            {{
              __(
                "Leave unticked for festivals that move (Diwali, Onam, Eid) and add them again next year."
              )
            }}
          </p>
        </div>
        <FormControl
          v-model="form.idea"
          type="textarea"
          :rows="3"
          :label="__('Post idea')"
          :placeholder="
            __('Becomes the brief of the post planned for this day')
          "
        />
        <ErrorMessage :message="error" />
      </form>
    </template>
    <template #actions>
      <div class="flex items-center justify-between gap-2">
        <Button
          v-if="occasion"
          variant="ghost"
          theme="red"
          :label="__('Delete')"
          :loading="deleting"
          @click="remove"
        />
        <span v-else />
        <div class="flex gap-2">
          <Button :label="__('Cancel')" @click="open = false" />
          <Button
            variant="solid"
            type="submit"
            form="occasion-form"
            :label="__('Save')"
            :loading="saving"
            :disabled="saving"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import {
  Button,
  call,
  Dialog,
  ErrorMessage,
  FormControl,
  toast,
} from "frappe-ui";
import { reactive, ref, watch } from "vue";

export interface Occasion {
  name: string;
  occasion_name: string;
  date: string;
  occasion_date: string;
  region: string;
  idea?: string;
  repeats_yearly: boolean;
}

const open = defineModel<boolean>("open", { default: false });
const props = defineProps<{ occasion: Occasion | null; date?: string }>();
const emit = defineEmits<{ saved: [] }>();

const REGIONS = [
  { label: __("Everywhere"), value: "Everywhere" },
  { label: __("India"), value: "India" },
  { label: __("Kerala"), value: "Kerala" },
  { label: __("UAE"), value: "UAE" },
];

const form = reactive({
  occasion_name: "",
  occasion_date: "",
  region: "India",
  repeats_yearly: false,
  idea: "",
});
const saving = ref(false);
const deleting = ref(false);
const error = ref("");

watch(open, (isOpen) => {
  if (!isOpen) return;
  error.value = "";
  const o = props.occasion;
  Object.assign(form, {
    occasion_name: o?.occasion_name || "",
    // a yearly occasion is edited on the date shown for this year
    occasion_date: o
      ? o.repeats_yearly
        ? o.date
        : o.occasion_date
      : props.date || "",
    region: o?.region || "India",
    repeats_yearly: !!o?.repeats_yearly,
    idea: o?.idea || "",
  });
});

async function save() {
  if (!form.occasion_name.trim() || !form.occasion_date) {
    error.value = __("Add the occasion's name and date.");
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    await call("helpdesk.api.content_plans.save_occasion", {
      name: props.occasion?.name,
      values: { ...form, repeats_yearly: form.repeats_yearly ? 1 : 0 },
    });
    toast.success(__("Occasion saved"));
    emit("saved");
    open.value = false;
  } catch (e: any) {
    error.value = e?.messages?.[0] || __("Couldn't save the occasion.");
  } finally {
    saving.value = false;
  }
}

async function remove() {
  if (!props.occasion) return;
  deleting.value = true;
  try {
    await call("helpdesk.api.content_plans.delete_occasion", {
      name: props.occasion.name,
    });
    toast.success(__("Occasion deleted"));
    emit("saved");
    open.value = false;
  } catch (e: any) {
    error.value = e?.messages?.[0] || __("Couldn't delete the occasion.");
  } finally {
    deleting.value = false;
  }
}
</script>
