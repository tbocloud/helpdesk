<template>
  <p v-if="!payments.length" class="text-p-sm text-ink-gray-6">
    {{ __("No payments.") }}
  </p>
  <div v-else class="overflow-x-auto">
    <table class="w-full min-w-[32rem] text-sm">
      <thead class="text-left text-xs text-ink-gray-6">
        <tr>
          <th class="py-1 pe-3 font-normal">{{ __("Payment") }}</th>
          <th class="py-1 pe-3 font-normal">{{ __("Date") }}</th>
          <th class="py-1 pe-3 font-normal">{{ __("Lead or customer") }}</th>
          <th class="py-1 text-right font-normal">{{ __("Amount") }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(payment, i) in payments"
          :key="i"
          class="border-t border-outline-gray-1"
        >
          <td class="py-1.5 pe-3 font-mono text-ink-gray-8">
            {{ payment.payment_entry }}
            <span
              v-if="payment.kind !== 'Receipt'"
              class="block font-sans text-xs text-ink-gray-6"
              >{{ payment.kind }}</span
            >
          </td>
          <td class="py-1.5 pe-3 font-mono tabular-nums text-ink-gray-7">
            {{ payment.date }}
          </td>
          <td class="py-1.5 pe-3 text-ink-gray-7">
            {{ payment.lead || payment.customer || "–" }}
          </td>
          <td class="py-1.5 text-right font-mono tabular-nums text-ink-gray-9">
            {{ fullAmount(payment.amount, currency) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { fullAmount } from "./business/businessFormat";

defineProps<{
  payments: {
    payment_entry: string;
    date: string;
    kind: string;
    amount: number;
    lead: string | null;
    customer: string | null;
  }[];
  currency: string;
}>();
</script>
