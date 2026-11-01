<template>
  <fieldset class="flex flex-col gap-2">
    <legend class="text-sm text-ink-gray-7">{{ __("Slabs") }}</legend>
    <div
      v-for="(slab, i) in slabs"
      :key="i"
      role="group"
      :aria-label="__('Slab {0}', String(i + 1))"
      class="grid grid-cols-[1fr_1fr_5rem_auto] items-end gap-2"
    >
      <FormControl
        v-model="slab.from_amount"
        type="number"
        min="0"
        :label="i === 0 ? __('From') : undefined"
        :aria-label="__('Slab {0} from', String(i + 1))"
      />
      <FormControl
        v-model="slab.to_amount"
        type="number"
        min="0"
        :placeholder="__('No limit')"
        :label="i === 0 ? __('To') : undefined"
        :aria-label="__('Slab {0} to', String(i + 1))"
      />
      <FormControl
        v-model="slab.rate"
        type="number"
        min="0"
        max="100"
        step="0.1"
        :label="i === 0 ? __('Rate %') : undefined"
        :aria-label="__('Slab {0} rate', String(i + 1))"
      />
      <Button
        variant="ghost"
        :label="__('Remove slab {0}', String(i + 1))"
        @click="slabs.splice(i, 1)"
      >
        <template #icon>
          <LucideTrash2 class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
    <div>
      <Button :label="__('Add slab')" @click="add">
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
  </fieldset>
</template>

<script setup lang="ts">
import type { SlabForm } from "@/pages/leads/commission";
import { __ } from "@/translation";
import { Button, FormControl } from "frappe-ui";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";

const slabs = defineModel<SlabForm[]>({ required: true });

/** A new slab starts where the last one ends. */
function add() {
  const last = slabs.value[slabs.value.length - 1];
  slabs.value.push({
    from_amount: last && last.to_amount ? Number(last.to_amount) : "",
    to_amount: "",
    rate: "",
  });
}
</script>
