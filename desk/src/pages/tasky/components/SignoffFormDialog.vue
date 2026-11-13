<template>
  <!-- bare: the header and the buttons stay put while the form scrolls between them -->
  <Dialog
    :open="open"
    size="4xl"
    bare
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <div class="flex max-h-[calc(100vh-4rem)] flex-col">
      <header
        class="flex items-center gap-2 border-b border-outline-gray-1 px-4 py-3 sm:px-6"
      >
        <h2 class="flex-1 text-xl-semibold text-ink-gray-9">{{ title }}</h2>
        <Button
          v-if="canExpand"
          variant="ghost"
          :aria-label="__('Edit in full page')"
          :title="__('Edit in full page')"
          @click="editInFullPage"
        >
          <template #icon
            ><LucideMaximize2 class="size-4" aria-hidden="true"
          /></template>
        </Button>
        <Button
          variant="ghost"
          :aria-label="__('Close')"
          @click="emit('update:open', false)"
        >
          <template #icon
            ><LucideX class="size-4" aria-hidden="true"
          /></template>
        </Button>
      </header>

      <div class="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6">
        <TaskyState
          v-if="f.options.error"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the form')"
          :message="
            errorText(
              f.options.error,
              __('Check your connection, then try again.')
            )
          "
        >
          <Button :label="__('Try again')" @click="f.options.reload()" />
        </TaskyState>

        <div
          v-else-if="!f.data"
          class="flex flex-col gap-4"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div v-for="i in 4" :key="i" class="flex flex-col gap-1.5">
            <div class="h-3 w-24 animate-pulse rounded bg-surface-gray-2" />
            <div class="h-8 w-full animate-pulse rounded bg-surface-gray-1" />
          </div>
        </div>

        <div
          v-else-if="!f.data.customer"
          role="alert"
          class="flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-p-sm text-warning"
        >
          <LucideTriangleAlert
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <span>{{
            __(
              "This project has no customer. Set the customer on the project first; the person who signs off must be one of its contacts."
            )
          }}</span>
        </div>

        <form v-else novalidate @submit.prevent="askToSend">
          <SignoffFields :f="f" />
          <div
            v-if="f.errorMessage"
            role="alert"
            class="mt-4 flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
          >
            <LucideCircleAlert
              class="mt-0.5 size-4 shrink-0"
              aria-hidden="true"
            />
            <span>{{ f.errorMessage }}</span>
          </div>
        </form>
      </div>

      <footer class="border-t border-outline-gray-1 px-4 py-3 sm:px-6">
        <div
          class="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end"
        >
          <Button
            v-if="canExpand"
            class="sm:mr-auto"
            :label="__('Edit in full page')"
            @click="editInFullPage"
          >
            <template #prefix
              ><LucideMaximize2 class="size-4" aria-hidden="true"
            /></template>
          </Button>
          <Button :label="__('Cancel')" @click="emit('update:open', false)" />
          <template v-if="f.data?.customer">
            <Button
              :label="__('Save as draft')"
              :loading="f.saving === 'draft'"
              :disabled="!!f.saving"
              @click="save(false)"
            />
            <!-- the reason it can't go yet is its tooltip and, on a phone, under it -->
            <Button
              v-if="f.data.can_send"
              variant="solid"
              :label="__('Send to customer')"
              :disabled="!!f.sendBlocked || !!f.saving"
              :title="f.sendBlocked || undefined"
              @click="askToSend"
            >
              <template #prefix>
                <LucideSend class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </template>
        </div>
        <p
          v-if="f.data?.customer && f.data.can_send && f.sendBlocked"
          class="mt-2 text-right text-p-xs text-ink-gray-6"
        >
          {{ f.sendBlocked }}
        </p>
      </footer>
    </div>
  </Dialog>

  <SignoffSendConfirm
    v-model:open="confirmSend"
    :name="f.signatory?.full_name || ''"
    :email="f.signatory?.email || ''"
    :cc="f.ccList"
    :loading="f.saving === 'send'"
    @send="save(true)"
  />
</template>

<script setup lang="ts">
import TaskyState from "@/components/TaskyState.vue";
import { useSignoffDraftStore } from "@/stores/signoffDraft";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, Dialog } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideMaximize2 from "~icons/lucide/maximize-2";
import LucideSend from "~icons/lucide/send";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideX from "~icons/lucide/x";
import { useSignoffForm } from "../useSignoffForm";
import SignoffFields from "./SignoffFields.vue";
import SignoffSendConfirm from "./SignoffSendConfirm.vue";

/** New sign-off: set up, fill in and send it in one dialog, or take it to the full page. */
const props = defineProps<{
  open: boolean;
  projectId: string;
  /** a UAT: its tests come from the SRS of the plan the project was made from */
  uat?: boolean;
  /** opened from this lead's page: its owner may send it without opening the project */
  lead?: string | null;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  /** saved (`sent`: and sent to the customer) */
  saved: [name: string, sent: boolean];
}>();

const router = useRouter();
const drafts = useSignoffDraftStore();

const f = useSignoffForm({
  projectId: () => props.projectId,
  lead: () => props.lead,
  uat: () => !!props.uat,
});

watch(
  () => props.open,
  (open) => open && f.start(),
  { immediate: true }
);

const title = computed(() =>
  f.isUat ? __("New UAT sign-off") : __("New sign-off")
);
// the full page is the project's: not from a lead's page, whose owner may not open it
const canExpand = computed(() => !props.lead && !!f.data?.customer);

const confirmSend = ref(false);
function askToSend() {
  if (f.sendBlocked) {
    f.errorMessage = f.sendBlocked;
    return;
  }
  f.errorMessage = "";
  confirmSend.value = true;
}

async function save(send: boolean) {
  const name = await f.submit(send);
  confirmSend.value = false;
  if (!name) return;
  emit("update:open", false);
  emit("saved", name, send);
}

/** Everything typed goes along; nothing is saved until the page saves it. */
function editInFullPage() {
  drafts.keep(props.projectId, !!props.uat, f.carry());
  emit("update:open", false);
  router.push({
    name: "TaskySignoffNew",
    params: { projectId: props.projectId },
    query: props.uat ? { uat: "1" } : {},
  });
}
</script>
