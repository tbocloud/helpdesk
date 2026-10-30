<template>
  <fieldset
    class="flex flex-col gap-4 rounded-lg border border-outline-gray-2 p-4"
  >
    <legend class="px-1 text-sm-medium text-ink-gray-8">
      {{ __("Daily call batches") }}
    </legend>
    <Switch
      v-model="rules.call_batches_enabled"
      :label="__('Hand out daily call batches')"
      :description="
        __(
          'Each member gets a set number of leads per time slot and has to call them in it. Members then see Today\'s calls instead of Call today.'
        )
      "
    />

    <template v-if="rules.call_batches_enabled">
      <div class="flex flex-col gap-2">
        <FormLabel :label="__('Time slots')" size="md" />
        <ul role="list" class="flex flex-col gap-3">
          <li
            v-for="(slot, index) in rules.call_slots"
            :key="index"
            class="grid grid-cols-2 items-end gap-2 sm:grid-cols-[minmax(0,1.5fr)_1fr_1fr_6rem_auto]"
          >
            <FormControl
              v-model="slot.label"
              class="col-span-2 sm:col-span-1"
              :label="__('Name')"
              maxlength="40"
              autocomplete="off"
            />
            <FormControl
              v-model="slot.start_time"
              type="time"
              :label="__('From')"
            />
            <FormControl
              v-model="slot.end_time"
              type="time"
              :label="__('To')"
            />
            <FormControl
              v-model="slot.size"
              type="number"
              min="1"
              :label="__('Calls')"
            />
            <Button
              class="justify-self-end"
              variant="ghost"
              :label="__('Remove {0}', slot.label || __('slot'))"
              :disabled="rules.call_slots.length < 2"
              @click="rules.call_slots.splice(index, 1)"
            >
              <template #icon>
                <LucideTrash2 class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </li>
        </ul>
        <Button class="self-start" :label="__('Add slot')" @click="addSlot">
          <template #prefix>
            <LucidePlus class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl
          v-model="rules.daily_call_cap"
          type="number"
          min="1"
          :label="__('Calls a day per person')"
          :description="__('Slots stop handing out leads at this number.')"
        />
        <FormControl
          v-model="rules.overdue_block_limit"
          type="number"
          min="0"
          :label="__('Overdue calls that block the next batch')"
          :description="
            __('Above this many, the heads are told at the end of a slot.')
          "
        />
      </div>
      <Switch
        v-model="rules.pull_unassigned"
        :label="__('Pull unassigned leads')"
        :description="
          __(
            'When a batch has room left, give the person this department\'s open leads that have no owner.'
          )
        "
      />

      <details class="group">
        <summary
          class="cursor-pointer rounded text-sm text-ink-gray-7 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        >
          {{ __("Campaign filter (optional)") }}
        </summary>
        <div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <FormControl
            v-model="rules.campaign_industry"
            :label="__('Industry')"
            autocomplete="off"
          />
          <FormControl
            v-model="rules.campaign_state"
            :label="__('State')"
            autocomplete="off"
          />
          <FormControl
            v-model="rules.campaign_district"
            :label="__('District')"
            autocomplete="off"
          />
        </div>
        <p class="mt-2 text-p-xs text-ink-gray-6">
          {{
            __(
              "New leads in a batch are only of this industry, state or district. Follow-ups due are always included."
            )
          }}
        </p>
      </details>

      <details v-if="members.length" class="group">
        <summary
          class="cursor-pointer rounded text-sm text-ink-gray-7 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        >
          {{ __("Daily limit for one person (optional)") }}
        </summary>
        <ul role="list" class="mt-3 flex flex-col gap-2">
          <li
            v-for="member in members"
            :key="member.value"
            class="flex items-center justify-between gap-3"
          >
            <span class="min-w-0 truncate text-p-sm text-ink-gray-8">{{
              member.label
            }}</span>
            <FormControl
              v-model="rules.member_caps[member.value]"
              type="number"
              min="1"
              class="w-28"
              :aria-label="__('Calls a day for {0}', member.label)"
              :placeholder="String(rules.daily_call_cap)"
            />
          </li>
        </ul>
      </details>
    </template>
  </fieldset>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, FormControl, FormLabel, Switch } from "frappe-ui";
import LucidePlus from "~icons/lucide/plus";
import LucideTrash2 from "~icons/lucide/trash-2";
import type { CallRules } from "@/pages/leads/callBatches";

const rules = defineModel<CallRules>({ required: true });
defineProps<{ members: { label: string; value: string }[] }>();

function addSlot() {
  const last = rules.value.call_slots.at(-1);
  rules.value.call_slots.push({
    label: "",
    start_time: last?.end_time ?? "10:00",
    end_time: "",
    size: 50,
  });
}
</script>
