<template>
  <section
    :aria-labelledby="id"
    class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3"
  >
    <div class="flex min-w-0 flex-col">
      <h2 :id="id" class="text-xs text-ink-gray-6">{{ __("Calling for") }}</h2>
      <p class="truncate text-base-medium text-ink-gray-9">
        {{ focusLabel(focus) }}
      </p>
    </div>
    <Button v-if="canSwitch(options)" :label="__('Change')" @click="openPicker">
      <template #prefix>
        <LucideArrowLeftRight class="size-4" aria-hidden="true" />
      </template>
    </Button>

    <Dialog
      v-model:open="show"
      :title="__('What are you calling for?')"
      size="md"
    >
      <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
        <div
          class="flex flex-col gap-2"
          role="radiogroup"
          :aria-label="__('What are you calling for?')"
        >
          <button
            v-for="choice in choices"
            :key="choice.key"
            type="button"
            role="radio"
            :aria-checked="picked === choice.key"
            class="flex min-h-12 flex-col justify-center rounded-xl border px-4 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            :class="
              picked === choice.key
                ? 'border-brand bg-brand-soft'
                : 'border-outline-gray-2 bg-surface-base hover:bg-surface-gray-1'
            "
            @click="pick(choice.key)"
          >
            <span class="text-base-medium text-ink-gray-9">{{
              choice.label
            }}</span>
            <span v-if="choice.hint" class="text-p-sm text-ink-gray-6">{{
              choice.hint
            }}</span>
          </button>
          <button
            v-if="options.length > 1"
            type="button"
            role="radio"
            :aria-checked="picked === ALL"
            class="flex min-h-12 items-center rounded-xl border px-4 py-2 text-left text-base-medium text-ink-gray-9 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            :class="
              picked === ALL
                ? 'border-brand bg-brand-soft'
                : 'border-outline-gray-2 bg-surface-base hover:bg-surface-gray-1'
            "
            @click="pick(ALL)"
          >
            {{ __("All my departments") }}
          </button>
        </div>

        <FormControl
          v-if="districts.length > 1 && selected"
          v-model="district"
          type="select"
          :label="__('District (optional)')"
          :options="districtOptions"
          :disabled="!!selected.option.locked_district"
        />

        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "Your next calls will be for this. Calls already on your list stay there until you call them."
            )
          }}
        </p>
      </form>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="show = false" />
          <Button
            variant="solid"
            :label="__('Start calling')"
            :loading="saving"
            @click="submit"
          />
        </div>
      </template>
    </Dialog>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, Dialog, FormControl, toast } from "frappe-ui";
import { computed, ref, useId } from "vue";
import LucideArrowLeftRight from "~icons/lucide/arrow-left-right";
import {
  canSwitch,
  focusChoices,
  focusLabel,
  useSetFocus,
  type CallFocus,
  type FocusOption,
} from "./callBatches";

const props = defineProps<{
  focus: CallFocus | null;
  options: FocusOption[];
}>();
const emit = defineEmits<{ (e: "changed"): void }>();

const ALL = "__all__";
const id = `calling-for-${useId()}`;
const show = ref(false);
const picked = ref("");
const district = ref("");
const setFocus = useSetFocus();
const saving = computed(() => setFocus.loading);

const choices = computed(() => focusChoices(props.options));
const selected = computed(() =>
  choices.value.find((c) => c.key === picked.value)
);
const districts = computed(() => selected.value?.option.districts ?? []);
const districtOptions = computed(() => [
  { label: __("Any district"), value: "" },
  ...districts.value.map((d) => ({ label: d, value: d })),
]);

function pick(key: string) {
  picked.value = key;
  district.value = selected.value?.option.locked_district ?? "";
}

function openPicker() {
  const now = props.focus;
  picked.value = now
    ? now.product
      ? `${now.department}|${now.product}`
      : now.department
    : choices.value.length === 1
    ? choices.value[0].key
    : ALL;
  district.value = now?.district ?? "";
  show.value = true;
}

function submit() {
  const choice = selected.value;
  setFocus.submit(
    {
      department: choice?.department ?? "",
      product: choice?.product ?? "",
      district: choice ? district.value : "",
    },
    {
      onSuccess(result: { message?: string }) {
        show.value = false;
        toast.success(result.message || __("Done"));
        emit("changed");
      },
      onError(e: unknown) {
        toast.error(errorText(e, __("Couldn't switch. Try again.")));
      },
    }
  );
}
</script>
