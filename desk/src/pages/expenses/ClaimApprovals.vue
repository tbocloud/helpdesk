<template>
  <section
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-label="__('Claims to approve')"
  >
    <TaskyState
      v-if="!approvals.length"
      class="py-10"
      :icon="LucideCircleCheck"
      :title="__('Nothing to approve')"
      :message="__('Claims sent to you show here until you decide them.')"
    />
    <ul v-else class="divide-y divide-outline-gray-1">
      <li
        v-for="row in approvals"
        :key="row.ref"
        class="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center"
      >
        <div class="flex min-w-0 flex-1 items-center gap-3">
          <PersonAvatar :name="row.who" size="lg" />
          <div class="min-w-0">
            <p class="truncate text-base font-medium text-ink-gray-9">
              {{ row.who }}
            </p>
            <p class="truncate text-sm text-ink-gray-6">
              {{ row.title }}
              <template v-if="row.detail"> · {{ row.detail }}</template>
              · {{ dayjs(row.from_date).format("D MMM YYYY") }} ·
              <span class="font-mono">{{ row.ref }}</span>
            </p>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2 sm:justify-end">
          <span
            class="mr-1 font-mono text-base font-semibold tabular-nums text-ink-gray-9"
          >
            {{ money(row.amount, currency) }}
          </span>
          <Button
            v-if="row.receipt"
            :link="receiptUrl(row.ref, row.receipt)"
            :aria-label="__('Open the receipt of {0}', row.ref)"
            :tooltip="__('Receipt')"
          >
            <template #icon>
              <LucideReceipt class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <Button
            v-if="row.can_reject"
            :label="__('Reject')"
            :disabled="!!deciding"
            @click="rejecting = row"
          />
          <Button
            variant="subtle"
            :label="__('Approve')"
            :loading="deciding === row.ref"
            :disabled="!!deciding && deciding !== row.ref"
            @click="decide(row, true)"
          >
            <template #prefix>
              <LucideCheck class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
      </li>
    </ul>

    <Dialog
      :open="!!rejecting"
      :title="__('Reject {0}\'s claim', rejecting?.who || '')"
      @update:open="(value: boolean) => !value && (rejecting = null)"
    >
      <form
        :id="formId"
        @submit.prevent="rejecting && decide(rejecting, false)"
      >
        <FormControl
          v-model="reason"
          type="textarea"
          size="md"
          :rows="3"
          :label="__('Why? They will see this.')"
          required
        />
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            theme="red"
            type="submit"
            :form="formId"
            :label="__('Reject claim')"
            :disabled="!reason.trim()"
            :loading="!!deciding"
          />
        </div>
      </template>
    </Dialog>
  </section>
</template>

<script setup lang="ts">
import PersonAvatar from "@/components/PersonAvatar.vue";
import TaskyState from "@/components/TaskyState.vue";
import { money } from "@/components/invoicing/invoices";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, dayjs, Dialog, FormControl, toast } from "frappe-ui";
import { ref, useId, watch } from "vue";
import LucideCheck from "~icons/lucide/check";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideReceipt from "~icons/lucide/receipt";
import { receiptUrl, type Approval } from "./expenses";

defineProps<{ approvals: Approval[]; currency: string }>();
const emit = defineEmits<{ (e: "decided"): void }>();

const formId = useId();
const deciding = ref<string | null>(null);
const rejecting = ref<Approval | null>(null);
const reason = ref("");

watch(rejecting, () => (reason.value = ""));

async function decide(row: Approval, approve: boolean) {
  if (deciding.value) return;
  deciding.value = row.ref;
  try {
    await call("helpdesk.api.expenses.decide_expense", {
      name: row.ref,
      approve: approve ? 1 : 0,
      reason: approve ? null : reason.value,
    });
    toast.success(
      approve
        ? __("{0}'s claim approved", row.who)
        : __("{0}'s claim rejected", row.who)
    );
    rejecting.value = null;
    emit("decided");
  } catch (e) {
    toast.error(errorText(e, __("Couldn't save your decision. Try again.")));
  } finally {
    deciding.value = null;
  }
}
</script>
