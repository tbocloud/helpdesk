<template>
  <PanelSection
    v-if="visible"
    :title="__('Customization estimate')"
    :icon="LucideWrench"
    :level="3"
  >
    <template v-if="STATUS[estimate.status]" #actions>
      <TaskyBadge v-bind="STATUS[estimate.status]" />
    </template>

    <div aria-live="polite" class="flex flex-col gap-3">
      <!-- Approved: the next step is the task -->
      <template v-if="estimate.status === 'Approved'">
        <p class="text-p-sm text-ink-gray-8">
          {{
            __(
              "{0} hours, delivery {1}.",
              String(estimate.hours),
              formatDay(estimate.delivery_date)
            )
          }}
          <span v-if="estimate.decided_by" class="text-ink-gray-5">
            {{ __("Approved by {0}.", estimate.decided_by) }}
          </span>
        </p>
        <Button
          variant="solid"
          :label="__('Create task')"
          @click="showCreateTask = true"
        >
          <template #prefix
            ><LucideListPlus class="size-4" aria-hidden="true"
          /></template>
        </Button>
        <p class="text-p-xs text-ink-gray-5">
          {{
            __(
              "The task gets the agreed date and hours unless you change them."
            )
          }}
        </p>
      </template>

      <!-- Waiting for the customer -->
      <template v-else-if="estimate.status === 'Sent'">
        <p class="text-p-sm text-ink-gray-8">
          {{
            __(
              "Sent: {0} hours, ready {1} once approved. Waiting for the customer.",
              String(estimate.hours),
              formatDay(estimate.delivery_date)
            )
          }}
        </p>
        <div class="flex flex-wrap gap-2">
          <Button
            :label="__('Customer approved')"
            :loading="deciding === 'approve'"
            @click="decide(true)"
          />
          <Button
            variant="ghost"
            :label="__('Customer declined')"
            :loading="deciding === 'decline'"
            @click="decide(false)"
          />
        </div>
        <p class="text-p-xs text-ink-gray-5">
          {{
            __(
              "Use these when the customer answers by email or phone instead of the portal."
            )
          }}
        </p>
      </template>

      <!-- Estimating (AI first draft, or declined and re-estimating) -->
      <template v-else>
        <p
          v-if="estimate.status === 'Estimated' && estimate.note"
          class="flex items-start gap-1.5 text-p-sm text-ink-gray-6"
        >
          <LucideSparkles
            class="mt-0.5 size-3.5 shrink-0 text-ink-gray-5"
            aria-hidden="true"
          />
          {{ __("AI estimate: {0}", estimate.note) }}
        </p>
        <form
          :id="formId"
          class="flex flex-col gap-3"
          novalidate
          @submit.prevent="send"
        >
          <div class="grid grid-cols-2 gap-2">
            <FormControl
              v-model.number="form.hours"
              type="number"
              min="0.5"
              step="0.5"
              :label="__('Hours')"
            />
            <FormControl
              v-model="form.delivery_date"
              type="date"
              :label="__('Ready by')"
            />
          </div>
          <p class="text-p-xs text-ink-gray-5">
            {{
              __(
                "Counted at {0} development hours per working day.",
                String(estimate.hours_per_day)
              )
            }}
          </p>
          <FormControl
            v-model="form.note"
            type="textarea"
            :rows="2"
            :label="__('Note for the customer (optional)')"
            :placeholder="
              __('What is included, assumptions, what they need to test')
            "
          />
          <p v-if="error" role="alert" class="text-p-sm text-danger">
            {{ error }}
          </p>
          <div class="flex flex-wrap gap-2">
            <Button
              variant="solid"
              type="submit"
              :form="formId"
              :label="__('Send estimate')"
              :loading="sending"
              :disabled="!canSend"
            />
            <Button
              v-if="estimate.status === 'Estimated'"
              variant="ghost"
              :label="__('Customer already approved')"
              :loading="deciding === 'approve'"
              @click="decide(true)"
            />
          </div>
        </form>
      </template>
    </div>
  </PanelSection>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import {
  Button,
  call,
  createResource,
  dayjs,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideClock from "~icons/lucide/clock";
import LucideListPlus from "~icons/lucide/list-plus";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideWrench from "~icons/lucide/wrench";
import TaskyBadge from "@/components/TaskyBadge.vue";
import type { Tone } from "@/components/tone";
import { showCreateTask } from "@/pages/ticket/modalStates";
import type { Component } from "vue";
import PanelSection from "./PanelSection.vue";

interface Estimate {
  is_customization: boolean;
  hours: number;
  status: "" | "Estimated" | "Sent" | "Approved" | "Declined";
  note: string;
  delivery_date: string | null;
  suggested_delivery: string | null;
  hours_per_day: number;
  off_days: number[];
  decided_by: string | null;
  can_manage: boolean;
}

const props = defineProps<{ ticketId: string }>();
const emit = defineEmits<{ changed: [] }>();

const STATUS: Record<string, { label: string; tone: Tone; icon: Component }> = {
  Estimated: { label: __("AI estimate"), tone: "info", icon: LucideSparkles },
  Sent: {
    label: __("Waiting for approval"),
    tone: "warning",
    icon: LucideClock,
  },
  Approved: {
    label: __("Approved"),
    tone: "success",
    icon: LucideCircleCheck,
  },
  Declined: { label: __("Declined"), tone: "danger", icon: LucideCircleX },
};

const formId = `estimate-form-${useId()}`;

const resource = createResource({
  url: "helpdesk.api.customization.get_estimate",
  makeParams: () => ({ ticket: props.ticketId }),
  auto: true,
  onSuccess: (data: Estimate) => fill(data),
});
const estimate = computed<Estimate>(
  () => resource.data ?? ({ status: "", hours_per_day: 6 } as Estimate)
);
const visible = computed(
  () =>
    !!resource.data?.can_manage &&
    (estimate.value.is_customization || !!estimate.value.status)
);

watch(
  () => props.ticketId,
  () => resource.reload()
);

const form = reactive({
  hours: 0 as number | string,
  delivery_date: "",
  note: "",
});

function fill(data: Estimate) {
  form.hours = data.hours || "";
  form.delivery_date = data.delivery_date || data.suggested_delivery || "";
  form.note = data.status === "Estimated" ? "" : data.note || "";
}

// a new hour count suggests a new date, the same way the server counts it
watch(
  () => form.hours,
  (hours) => {
    const h = Number(hours);
    if (!(h > 0) || estimate.value.status === "Sent") return;
    const days = Math.max(
      1,
      Math.ceil(h / (estimate.value.hours_per_day || 6))
    );
    let day = dayjs();
    let counted = 1;
    while (counted < days) {
      day = day.add(1, "day");
      if (!(estimate.value.off_days ?? [0]).includes(day.day())) counted++;
    }
    form.delivery_date = day.format("YYYY-MM-DD");
  }
);

const canSend = computed(
  () => Number(form.hours) > 0 && !!form.delivery_date && !sending.value
);

const sending = ref(false);
const deciding = ref<"" | "approve" | "decline">("");
const error = ref("");

function formatDay(date: string | null) {
  return date ? dayjs(date).format("ddd D MMM") : "—";
}

async function send() {
  if (!canSend.value) return;
  sending.value = true;
  error.value = "";
  try {
    resource.setData(
      await call("helpdesk.api.customization.send_estimate", {
        ticket: props.ticketId,
        hours: form.hours,
        delivery_date: form.delivery_date,
        note: form.note,
      })
    );
    toast.success(__("Estimate sent to the customer"));
    emit("changed");
  } catch (e: any) {
    error.value = e?.messages?.[0] || __("Couldn't send the estimate.");
  } finally {
    sending.value = false;
  }
}

async function decide(approve: boolean) {
  deciding.value = approve ? "approve" : "decline";
  try {
    resource.setData(
      await call("helpdesk.api.customization.decide_estimate", {
        ticket: props.ticketId,
        approve: approve ? 1 : 0,
      })
    );
    toast.success(approve ? __("Estimate approved") : __("Estimate declined"));
    emit("changed");
  } catch (e: any) {
    toast.error(e?.messages?.[0] || __("Couldn't record the decision."));
  } finally {
    deciding.value = "";
  }
}
</script>
