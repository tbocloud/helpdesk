<template>
  <Dialog v-model:open="open" :options="{ size: '2xl' }" :dismissible="false">
    <template #body-title>
      <div class="flex flex-col gap-0.5">
        <h3 class="text-xl-semibold text-ink-gray-9">
          {{ plan ? __("Edit monthly plan") : __("New monthly plan") }}
        </h3>
        <p class="text-p-sm text-ink-gray-5">
          {{
            __(
              "Next month's posts are created as ideas on the planning day, with the team and their tasks."
            )
          }}
        </p>
      </div>
    </template>
    <template #body-content>
      <form
        id="plan-form"
        class="flex flex-col gap-5"
        novalidate
        @submit.prevent="save"
      >
        <Link
          v-model="form.customer"
          doctype="HD Customer"
          :label="__('Customer') + ' *'"
          :placeholder="__('Select customer')"
          :disabled="!!plan"
        />

        <fieldset class="flex flex-col gap-2">
          <legend class="mb-1 text-xs text-ink-gray-5">
            {{ __("What goes out each month") }}
          </legend>
          <div
            v-for="(row, i) in form.items"
            :key="i"
            class="grid grid-cols-[1fr_1fr_5.5rem_auto] items-end gap-2"
          >
            <FormControl
              v-model="row.channel"
              type="select"
              :options="CHANNELS"
              :label="i === 0 ? __('Platform') : undefined"
              :aria-label="__('Platform')"
            />
            <FormControl
              v-model="row.format"
              type="select"
              :options="FORMATS"
              :label="i === 0 ? __('Post type') : undefined"
              :aria-label="__('Post type')"
            />
            <FormControl
              v-model.number="row.posts_per_month"
              type="number"
              min="1"
              :label="i === 0 ? __('Per month') : undefined"
              :aria-label="__('Posts per month')"
            />
            <Button
              variant="ghost"
              :aria-label="__('Remove this line')"
              :disabled="form.items.length === 1"
              @click="form.items.splice(i, 1)"
            >
              <LucideX class="size-4" aria-hidden="true" />
            </Button>
          </div>
          <div class="flex items-center justify-between">
            <Button
              size="sm"
              variant="ghost"
              :label="__('Add line')"
              @click="addLine"
            >
              <template #prefix
                ><LucidePlus class="size-3.5" aria-hidden="true"
              /></template>
            </Button>
            <span class="text-p-sm text-ink-gray-6">
              {{ __("{0} posts a month", String(total)) }}
            </span>
          </div>
        </fieldset>

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Link
            v-for="role in TEAM_ROLES"
            :key="role.field"
            v-model="form[role.field]"
            doctype="User"
            :label="__(role.label)"
            :placeholder="__('Assign')"
          />
        </div>

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <FormControl
            v-model="form.posting_days"
            type="select"
            :label="__('Posting days')"
            :options="POSTING_DAYS"
          />
          <FormControl
            v-model="form.publish_time"
            type="select"
            :label="__('Publish time')"
            :options="TIMES"
          />
          <FormControl
            v-model="form.task_mode"
            type="select"
            :label="__('Tasks')"
            :options="TASK_MODES"
          />
        </div>

        <fieldset
          class="flex flex-col gap-2 rounded-lg bg-surface-gray-1 px-3 py-3"
        >
          <FormControl
            v-model="form.include_occasions"
            type="checkbox"
            :label="__('Put a post on occasion days')"
          />
          <p class="ps-6 text-p-sm text-ink-gray-5">
            {{
              __(
                "The nearest planned post moves onto each occasion (and Everywhere days) and gets its idea as the brief."
              )
            }}
          </p>
          <div v-if="form.include_occasions" class="flex flex-wrap gap-4 ps-6">
            <FormControl
              v-for="r in REGIONS"
              :key="r.field"
              v-model="form[r.field]"
              type="checkbox"
              :label="r.label"
            />
          </div>
        </fieldset>

        <fieldset class="flex flex-col gap-2">
          <FormControl
            v-model="form.ai_topics"
            type="checkbox"
            :label="__('Suggest topics with AI')"
          />
          <p class="ps-6 text-p-sm text-ink-gray-5">
            {{
              __(
                "After a month is planned, each planned post gets a topic and brief. Posts you've renamed are left alone."
              )
            }}
          </p>
          <FormControl
            v-if="form.ai_topics"
            v-model="form.about_brand"
            type="textarea"
            :rows="3"
            :label="__('About the brand')"
            :placeholder="
              __(
                'What they sell, who their customers are, their tone. The AI uses only this, so it never invents offers.'
              )
            "
          />
        </fieldset>

        <FormControl
          v-model="form.enabled"
          type="checkbox"
          :label="__('Plan automatically every month')"
        />

        <ErrorMessage :message="error" />
      </form>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="open = false" />
        <Button
          variant="solid"
          type="submit"
          form="plan-form"
          :label="__('Save plan')"
          :loading="saving"
          :disabled="saving"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import { __ } from "@/translation";
import {
  Button,
  call,
  Dialog,
  ErrorMessage,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import LucidePlus from "~icons/lucide/plus";
import LucideX from "~icons/lucide/x";
import { CHANNELS, FORMATS, TEAM_ROLES } from "../constants";

export interface PlanItem {
  channel: string;
  format: string;
  posts_per_month: number;
}

export interface ContentPlan {
  name: string;
  customer: string;
  enabled: number;
  posting_days: string;
  publish_time: string;
  task_mode: string;
  writer?: string;
  designer?: string;
  marketer?: string;
  include_occasions: number;
  occasions_india: number;
  occasions_kerala: number;
  occasions_uae: number;
  ai_topics: number;
  about_brand?: string;
  posts_per_month: number;
  last_planned_month?: string;
  next_month_planned: boolean;
  items: PlanItem[];
  team: Record<string, string>;
}

const open = defineModel<boolean>("open", { default: false });
const props = defineProps<{ plan: ContentPlan | null }>();
const emit = defineEmits<{ saved: [name: string] }>();

const POSTING_DAYS = [
  { label: __("Monday to Saturday"), value: "Monday to Saturday" },
  { label: __("Monday to Friday"), value: "Monday to Friday" },
  { label: __("Every day"), value: "Every day" },
];
const TIMES = Array.from({ length: 32 }, (_, i) => {
  const hour = 7 + Math.floor(i / 2);
  const value = `${String(hour).padStart(2, "0")}:${i % 2 ? "30" : "00"}`;
  const label = `${hour % 12 || 12}:${i % 2 ? "30" : "00"} ${
    hour < 12 ? "AM" : "PM"
  }`;
  return { label, value };
});
const TASK_MODES = [
  { label: __("Default (Content settings)"), value: "" },
  { label: __("One task per person"), value: "One task per person" },
  { label: __("One task for the post"), value: "One task for the post" },
  { label: __("No tasks"), value: "No tasks" },
];
const REGIONS = [
  { field: "occasions_india", label: __("India") },
  { field: "occasions_kerala", label: __("Kerala") },
  { field: "occasions_uae", label: __("UAE") },
] as const;

function blank() {
  return {
    customer: "",
    items: [
      { channel: "Instagram", format: "Post", posts_per_month: 8 },
    ] as PlanItem[],
    writer: "",
    designer: "",
    marketer: "",
    posting_days: "Monday to Saturday",
    publish_time: "10:00",
    task_mode: "",
    include_occasions: true,
    occasions_india: true,
    occasions_kerala: false,
    occasions_uae: false,
    ai_topics: true,
    about_brand: "",
    enabled: true,
  };
}

const form = reactive(blank());
const saving = ref(false);
const error = ref("");

watch(open, (isOpen) => {
  if (!isOpen) return;
  error.value = "";
  const p = props.plan;
  Object.assign(
    form,
    blank(),
    p
      ? {
          customer: p.customer,
          items: p.items.map((row) => ({ ...row })),
          writer: p.writer || "",
          designer: p.designer || "",
          marketer: p.marketer || "",
          posting_days: p.posting_days || "Monday to Saturday",
          publish_time: p.publish_time || "10:00",
          task_mode: p.task_mode || "",
          include_occasions: !!p.include_occasions,
          occasions_india: !!p.occasions_india,
          occasions_kerala: !!p.occasions_kerala,
          occasions_uae: !!p.occasions_uae,
          enabled: !!p.enabled,
          ai_topics: !!p.ai_topics,
          about_brand: p.about_brand || "",
        }
      : {}
  );
});

const total = computed(() =>
  form.items.reduce((n, row) => n + (Number(row.posts_per_month) || 0), 0)
);

function addLine() {
  form.items.push({ channel: "Instagram", format: "Reel", posts_per_month: 4 });
}

async function save() {
  if (!form.customer) {
    error.value = __("Pick the customer.");
    return;
  }
  if (form.items.some((row) => !(Number(row.posts_per_month) >= 1))) {
    error.value = __("Each line needs at least 1 post a month.");
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    const name = await call("helpdesk.api.content_plans.save_plan", {
      name: props.plan?.name,
      values: {
        ...form,
        enabled: form.enabled ? 1 : 0,
        include_occasions: form.include_occasions ? 1 : 0,
        occasions_india: form.occasions_india ? 1 : 0,
        occasions_kerala: form.occasions_kerala ? 1 : 0,
        occasions_uae: form.occasions_uae ? 1 : 0,
        ai_topics: form.ai_topics ? 1 : 0,
        about_brand: form.about_brand.trim(),
      },
    });
    toast.success(__("Plan saved"));
    emit("saved", name);
    open.value = false;
  } catch (e: any) {
    error.value = e?.messages?.[0] || __("Couldn't save the plan.");
  } finally {
    saving.value = false;
  }
}
</script>
