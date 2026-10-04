<template>
  <section
    v-if="estimate?.can_decide"
    class="mx-6 mt-6 flex flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-base p-4 md:mx-10"
    :aria-labelledby="headingId"
  >
    <h2 :id="headingId" class="text-base font-medium text-ink-gray-9">
      {{ __("Your estimate is ready") }}
    </h2>
    <dl class="grid grid-cols-2 gap-3 text-sm sm:max-w-md">
      <div>
        <dt class="text-xs text-ink-gray-5">{{ __("Work") }}</dt>
        <dd class="font-medium tabular-nums text-ink-gray-9">
          {{ __("{0} hours", String(estimate.hours)) }}
        </dd>
      </div>
      <div>
        <dt class="text-xs text-ink-gray-5">{{ __("Ready by") }}</dt>
        <dd class="font-medium text-ink-gray-9">
          {{ dayjs(estimate.delivery_date).format("dddd, D MMMM") }}
        </dd>
      </div>
    </dl>
    <p
      v-if="estimate.note"
      class="whitespace-pre-line text-p-sm text-ink-gray-7"
    >
      {{ estimate.note }}
    </p>
    <p class="text-p-sm text-ink-gray-6">
      {{
        __(
          "Approve to start the work. If you approve after today, the date may move by the days that passed."
        )
      }}
    </p>
    <div class="flex flex-wrap gap-2">
      <Button
        variant="solid"
        :label="__('Approve estimate')"
        :loading="deciding === 'approve'"
        :disabled="!!deciding"
        @click="decide(true)"
      />
      <Button
        :label="__('Decline')"
        :loading="deciding === 'decline'"
        :disabled="!!deciding"
        @click="decide(false)"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, call, createResource, dayjs, toast } from "frappe-ui";
import { computed, ref, useId } from "vue";

const props = defineProps<{ ticketId: string }>();
const emit = defineEmits<{ decided: [] }>();

const headingId = `estimate-banner-${useId()}`;
const resource = createResource({
  url: "helpdesk.api.customization.get_estimate",
  makeParams: () => ({ ticket: props.ticketId }),
  auto: true,
});
const estimate = computed(() => resource.data);
const deciding = ref<"" | "approve" | "decline">("");

async function decide(approve: boolean) {
  deciding.value = approve ? "approve" : "decline";
  try {
    resource.setData(
      await call("helpdesk.api.customization.decide_estimate", {
        ticket: props.ticketId,
        approve: approve ? 1 : 0,
      })
    );
    toast.success(
      approve
        ? __("Thank you. The team will start the work.")
        : __("Thank you. The team will be in touch.")
    );
    emit("decided");
  } catch (e: any) {
    toast.error(
      e?.messages?.[0] || __("Couldn't save your answer. Try again.")
    );
  } finally {
    deciding.value = "";
  }
}
</script>
