<template>
  <Dialog
    :open="open"
    :title="__('How did we do?')"
    :actions="[
      {
        disabled: !preset || setValue.loading,
        loading: setValue.loading,
        label: __('Close and send rating'),
        variant: 'solid',
        onClick: () =>
          setValue.submit({
            fieldname: {
              status: 'Closed',
              feedback: preset,
              feedback_extra: text,
            },
          }),
      },
    ]"
    @update:open="() => $emit('update:open', !open)"
  >
    <template #default>
      <div class="space-y-4 text-base text-ink-gray-7">
        <div class="flex flex-col gap-2">
          <div>
            <span> {{ __("Select a rating") }} </span>
            <span class="text-ink-red-6"> * </span>
          </div>
          <Rating
            v-model="rating"
            :max="5"
            size="sm"
            @update:model-value="onSelectRating"
          />
        </div>
        <div v-if="options.data?.length" class="space-y-2">
          <span> {{ __("Pick an option") }} </span>
          <span class="text-ink-red-6"> * </span>
          <div class="flex flex-wrap gap-2">
            <Button
              v-for="o in options.data"
              :key="o.name"
              :label="o.label"
              :variant="preset === o.name ? 'solid' : 'subtle'"
              :aria-pressed="preset === o.name"
              @click="preset = o.name"
            />
          </div>
        </div>
        <div class="space-y-2">
          <span> {{ __("Other") }} </span>
          <FormControl
            v-model="text"
            type="textarea"
            :placeholder="__('Tell us more')"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import { createListResource, createResource, Rating, toast } from "frappe-ui";
import { inject, ref } from "vue";
import { ITicket } from "./symbols";
import { __ } from "@/translation";

interface P {
  open: boolean;
}

interface E {
  (event: "update:open", open: boolean): void;
}

defineProps<P>();
const emit = defineEmits<E>();
const ticket = inject(ITicket);
const rating = ref(0);
const text = ref("");
const preset = ref(null);
const options = createListResource({
  doctype: "HD Ticket Feedback Option",
  fields: ["name", "label"],
  pageLength: 99999,
});
const setValue = createResource({
  url: "frappe.client.set_value",
  debounce: 300,
  makeParams: (params) => {
    return {
      doctype: "HD Ticket",
      name: ticket.data.name,
      fieldname: params.fieldname,
      value: params.value,
    };
  },
  onSuccess: () => {
    emit("update:open", false);
    ticket.reload();
  },
  onError: (error) => {
    toast.error(
      errorText(error, __("Your rating wasn't saved. Please try again."))
    );
  },
});
function onSelectRating(r: number) {
  preset.value = null;
  text.value = "";
  options.update({
    filters: {
      rating: r / 5,
      disabled: 0,
    },
  });
  options.reload();
}
</script>
