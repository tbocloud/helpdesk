<template>
  <div class="flex flex-col gap-2" role="group" :aria-labelledby="titleId">
    <div class="flex items-center justify-between gap-2">
      <h3 :id="titleId" class="text-base-medium text-ink-gray-9">
        {{ __("Numbers") }}
      </h3>
      <Button
        v-if="canWrite"
        variant="subtle"
        size="sm"
        :label="__('Add number')"
        @click="showAdd = true"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>

    <p v-if="!inUse.length" class="text-p-sm text-ink-gray-6">
      {{
        old.length
          ? __("No number in use. Add one, or bring an old one back.")
          : __("No number yet.")
      }}
    </p>
    <ul v-else role="list" class="flex flex-col">
      <li
        v-for="n in inUse"
        :key="n.id"
        class="flex min-h-11 items-center gap-2 border-b border-outline-gray-1 py-1.5 last:border-b-0"
      >
        <div class="flex min-w-0 flex-1 flex-col gap-0.5">
          <div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            <span class="font-mono text-base tabular-nums text-ink-gray-9">{{
              n.number
            }}</span>
            <TaskyBadge v-if="n.is_primary" tone="brand" :label="__('Main')" />
            <TaskyBadge
              v-if="n.status === 'Not reachable'"
              tone="warning"
              :icon="LucidePhoneOff"
              :label="__('Not reachable')"
            />
          </div>
          <p v-if="detail(n)" class="truncate text-p-xs text-ink-gray-6">
            {{ detail(n) }}
          </p>
        </div>
        <Button
          v-if="canCall"
          variant="subtle"
          :aria-label="__('Call {0}', n.number)"
          :tooltip="__('MyOperator rings your phone, then {0}', n.number)"
          :loading="dialing === n.number"
          @click="dial(n)"
        >
          <LucidePhone class="size-4" aria-hidden="true" />
        </Button>
        <Button
          v-else-if="n.tel"
          variant="subtle"
          :link="n.tel"
          :aria-label="__('Call {0}', n.number)"
          @click="remember(n, 'phone')"
        >
          <LucidePhone class="size-4" aria-hidden="true" />
        </Button>
        <Button
          v-if="n.whatsapp"
          variant="ghost"
          :link="n.whatsapp"
          :aria-label="__('WhatsApp {0}', n.number)"
        >
          <LucideMessageCircle class="size-4" aria-hidden="true" />
        </Button>
        <Dropdown v-if="canWrite" :options="menu(n)" placement="right">
          <Button
            variant="ghost"
            :aria-label="__('More for {0}', n.number)"
            :loading="busy === n.id"
          >
            <LucideEllipsis class="size-4" aria-hidden="true" />
          </Button>
        </Dropdown>
      </li>
    </ul>

    <div v-if="old.length" class="flex flex-col">
      <Button
        class="self-start"
        variant="ghost"
        size="sm"
        :label="
          showOld
            ? __('Hide old numbers')
            : __('Old numbers ({0})', String(old.length))
        "
        :aria-expanded="showOld"
        @click="showOld = !showOld"
      >
        <template #prefix>
          <component
            :is="showOld ? LucideChevronUp : LucideChevronDown"
            class="size-4"
            aria-hidden="true"
          />
        </template>
      </Button>
      <ul v-if="showOld" role="list" class="flex flex-col">
        <li
          v-for="n in old"
          :key="n.id"
          class="flex min-h-11 items-center gap-2 border-b border-outline-gray-1 py-1.5 last:border-b-0"
        >
          <div class="flex min-w-0 flex-1 flex-col gap-0.5">
            <div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <span
                class="font-mono text-base tabular-nums text-ink-gray-5 line-through decoration-outline-gray-3"
                >{{ n.number }}</span
              >
              <TaskyBadge :label="__(n.status)" />
            </div>
            <p v-if="detail(n)" class="truncate text-p-xs text-ink-gray-5">
              {{ detail(n) }}
            </p>
          </div>
          <Dropdown v-if="canWrite" :options="menu(n)" placement="right">
            <Button
              variant="ghost"
              :aria-label="__('More for {0}', n.number)"
              :loading="busy === n.id"
            >
              <LucideEllipsis class="size-4" aria-hidden="true" />
            </Button>
          </Dropdown>
        </li>
      </ul>
    </div>

    <p v-if="error" role="alert" class="text-p-sm text-danger">{{ error }}</p>

    <AddNumberDialog
      v-model:open="showAdd"
      :lead-id="leadId"
      :on-call="false"
      @saved="emit('changed')"
    />

    <Dialog
      v-model:open="showRemove"
      :title="__('Remove this number?')"
      size="sm"
    >
      <p class="text-p-sm text-ink-gray-7">
        {{
          __(
            "{0} is taken off the lead for good. To keep it on record, mark it Old or Wrong number instead.",
            removing?.number ?? ""
          )
        }}
      </p>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            theme="red"
            :label="__('Remove')"
            :loading="busy === removing?.id"
            @click="remove"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, Dialog, Dropdown, toast } from "frappe-ui";
import { computed, ref, useId } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronUp from "~icons/lucide/chevron-up";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideMessageCircle from "~icons/lucide/message-circle";
import LucidePhone from "~icons/lucide/phone";
import LucidePhoneOff from "~icons/lucide/phone-off";
import LucidePlus from "~icons/lucide/plus";
import AddNumberDialog from "./AddNumberDialog.vue";
import { isUsable, useClickToCall, type LeadNumber } from "./leads";
import { startCall } from "./pendingCalls";

const props = defineProps<{
  leadId: string;
  leadName: string;
  numbers: LeadNumber[];
  canWrite: boolean;
  /** MyOperator can ring for this person; else the number's tel: link dials */
  canCall: boolean;
  canRemove: boolean;
  /** the call in Today's calls this lead was opened from */
  batchItem?: string | null;
}>();
const emit = defineEmits<{ (e: "changed"): void }>();

const titleId = `numbers-${useId()}`;
const inUse = computed(() => props.numbers.filter(isUsable));
const old = computed(() => props.numbers.filter((n) => !isUsable(n)));
const showOld = ref(false);
const showAdd = ref(false);
const removing = ref<LeadNumber | null>(null);
const showRemove = computed({
  get: () => !!removing.value,
  set: (open: boolean) => {
    if (!open) removing.value = null;
  },
});
const busy = ref("");
const error = ref("");

/** Who it belongs to: "Decision-maker · Anil, Owner · after 5 pm". */
function detail(n: LeadNumber) {
  return [n.label, [n.person, n.designation].filter(Boolean).join(", "), n.note]
    .filter(Boolean)
    .join(" · ");
}

// ---------- calling ----------

const clickToCall = useClickToCall();
const dialing = computed(() =>
  clickToCall.loading
    ? String((clickToCall.params as { number?: string })?.number)
    : ""
);

/** The call waits for its result, which names the number that was dialled. */
function remember(n: LeadNumber, via: "phone" | "myoperator") {
  startCall({
    lead: props.leadId,
    lead_name: props.leadName,
    phone: n.number,
    number: n.number,
    item: props.batchItem,
    via,
  });
}
function dial(n: LeadNumber) {
  clickToCall.submit({ name: props.leadId, number: n.number });
  remember(n, "myoperator");
}

// ---------- changing a number ----------

function menu(n: LeadNumber) {
  const items = [];
  if (isUsable(n)) {
    if (!n.is_primary) {
      items.push({
        label: __("Make main number"),
        onClick: () => change(n, { make_primary: 1 }),
      });
    }
    items.push(
      n.status === "Not reachable"
        ? {
            label: __("Back in use"),
            onClick: () => change(n, { status: "Active" }),
          }
        : {
            label: __("Not reachable"),
            onClick: () => change(n, { status: "Not reachable" }),
          },
      {
        label: __("Wrong number"),
        onClick: () => change(n, { status: "Wrong number" }),
      },
      { label: __("Old number"), onClick: () => change(n, { status: "Old" }) }
    );
  } else {
    items.push({
      label: __("Back in use"),
      onClick: () => change(n, { status: "Active" }),
    });
  }
  if (props.canRemove) {
    items.push({ label: __("Remove"), onClick: () => (removing.value = n) });
  }
  return items;
}

function change(n: LeadNumber, values: Record<string, string | number>) {
  busy.value = n.id;
  error.value = "";
  call("helpdesk.api.leads.update_lead_number", {
    lead: props.leadId,
    number_id: n.id,
    ...values,
  })
    .then(() => {
      toast.success(__("Saved"));
      emit("changed");
    })
    .catch((e: unknown) => {
      error.value = errorText(e, __("Couldn't change the number. Try again."));
    })
    .finally(() => (busy.value = ""));
}

function remove() {
  const n = removing.value;
  if (!n) return;
  busy.value = n.id;
  call("helpdesk.api.leads.remove_lead_number", {
    lead: props.leadId,
    number_id: n.id,
  })
    .then(() => {
      toast.success(__("Number removed"));
      removing.value = null;
      emit("changed");
    })
    .catch((e: unknown) => {
      toast.error(errorText(e, __("Couldn't remove the number. Try again.")));
    })
    .finally(() => (busy.value = ""));
}
</script>
