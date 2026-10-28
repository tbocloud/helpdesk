<template>
  <div class="flex h-full flex-col">
    <ProjectNav :project-id="projectId">
      <template #actions>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="credentials.loading && !!credentials.data"
          @click="credentials.reload()"
        >
          <template #icon><LucideRefreshCw class="size-4" /></template>
        </Button>
      </template>
    </ProjectNav>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-5xl px-4 py-5 md:px-6">
        <p class="sr-only" aria-live="polite">{{ announcement }}</p>
        <TaskyState
          v-if="credentials.error && !credentials.data"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the credentials')"
          :message="
            errorText(
              credentials.error,
              __('Check your connection and try again.')
            )
          "
        >
          <Button :label="__('Retry')" @click="credentials.reload()" />
        </TaskyState>

        <div v-else-if="!data" class="flex flex-col gap-3" aria-busy="true">
          <div
            v-for="i in 2"
            :key="i"
            class="h-28 animate-pulse rounded-xl bg-surface-gray-1"
          />
        </div>

        <template v-else>
          <div class="mb-4 flex flex-wrap items-center gap-2">
            <h2 class="text-lg-semibold text-ink-gray-9">
              {{ __("Client credentials") }}
            </h2>
            <TaskyBadge
              v-if="closed"
              :label="__('Project closed')"
              :icon="LucideLock"
            />
            <div v-if="!closed" class="ml-auto flex flex-wrap gap-2">
              <Button
                v-if="received.length"
                theme="red"
                :label="__('Hand back & close')"
                @click="showHandBack = true"
              >
                <template #prefix>
                  <LucideUndo2 class="size-4" aria-hidden="true" />
                </template>
              </Button>
              <Button
                variant="solid"
                :label="__('Add credentials')"
                @click="openForm(null)"
              >
                <template #prefix>
                  <LucidePlus class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </div>
          </div>

          <p
            class="mb-4 flex items-start gap-2 text-p-sm text-ink-gray-6"
            role="note"
          >
            <LucideShieldCheck
              class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
            {{
              __(
                "Passwords stay hidden. Showing one is written to the project's timeline with your name."
              )
            }}
          </p>

          <TaskyState
            v-if="!data.handovers.length"
            :icon="LucideKeyRound"
            :title="__('No credentials yet')"
            :message="
              __(
                'When the client hands over their logins (Facebook, Instagram, the website …), record them here.'
              )
            "
          >
            <Button
              v-if="!closed"
              variant="solid"
              :label="__('Add credentials')"
              @click="openForm(null)"
            />
          </TaskyState>

          <ul v-else class="flex flex-col gap-4" role="list">
            <li
              v-for="h in data.handovers"
              :key="h.name"
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            >
              <div
                class="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-outline-gray-1 px-4 py-3"
              >
                <TaskyBadge
                  :label="__(h.direction)"
                  :icon="h.direction === RETURNED ? LucideUndo2 : LucideInbox"
                />
                <span class="text-sm text-ink-gray-7">
                  <template v-if="h.direction === RETURNED">
                    {{
                      __(
                        "Signed off by {0} on {1}",
                        h.client_signoff_name ?? "",
                        dateFormat(h.signed_on, "D MMM YYYY")
                      )
                    }}
                  </template>
                  <template v-else>
                    {{
                      __(
                        "From {0} on {1}",
                        h.handed_over_by ?? "",
                        dateFormat(h.handed_over_on, "D MMM YYYY")
                      )
                    }}
                    <template v-if="h.received_by_name">
                      · {{ __("received by {0}", h.received_by_name) }}
                    </template>
                  </template>
                </span>
                <Button
                  v-if="h.direction !== RETURNED && !closed"
                  class="ml-auto"
                  variant="ghost"
                  :label="__('Edit')"
                  @click="openForm(h)"
                >
                  <template #prefix>
                    <LucidePencil class="size-4" aria-hidden="true" />
                  </template>
                </Button>
              </div>
              <p
                v-if="h.close_reason"
                class="border-b border-outline-gray-1 px-4 py-2 text-p-sm text-ink-gray-7"
              >
                {{ __("Closed because: {0}", h.close_reason) }}
              </p>
              <ul role="list">
                <li
                  v-for="item in h.items"
                  :key="item.name"
                  class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-3 last:border-b-0 md:flex-row md:items-center md:gap-4"
                >
                  <div class="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span class="text-base-medium text-ink-gray-9">{{
                      item.platform
                    }}</span>
                    <a
                      v-if="item.account_url"
                      :href="safeUrl(item.account_url)"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="truncate rounded text-xs text-ink-gray-6 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                      >{{ item.account_url }}</a
                    >
                    <span
                      v-if="item.two_factor_contact"
                      class="text-xs text-ink-gray-6"
                      >{{
                        __("2FA code goes to {0}", item.two_factor_contact)
                      }}</span
                    >
                    <span v-if="item.notes" class="text-xs text-ink-gray-6">{{
                      item.notes
                    }}</span>
                  </div>
                  <span
                    class="font-mono text-sm text-ink-gray-8 md:w-56 md:truncate"
                    >{{ item.username || "–" }}</span
                  >
                  <div class="flex items-center gap-2 md:w-60 md:justify-end">
                    <span
                      v-if="h.direction === RETURNED"
                      class="text-xs text-ink-gray-6"
                      >{{ __("Handed back") }}</span
                    >
                    <template v-else-if="item.has_password">
                      <span
                        class="font-mono text-sm tabular-nums text-ink-gray-8"
                        :aria-label="
                          shown[item.name] ? __('Password') : __('Hidden')
                        "
                        >{{ shown[item.name] ?? "••••••••" }}</span
                      >
                      <Button
                        v-if="shown[item.name]"
                        :label="__('Hide')"
                        @click="hide(item.name)"
                      >
                        <template #prefix>
                          <LucideEyeOff class="size-4" aria-hidden="true" />
                        </template>
                      </Button>
                      <Button
                        v-else
                        :label="__('Show')"
                        :loading="revealing === item.name"
                        @click="reveal(h.name, item)"
                      >
                        <template #prefix>
                          <LucideEye class="size-4" aria-hidden="true" />
                        </template>
                      </Button>
                    </template>
                    <span v-else class="text-xs text-ink-gray-6">{{
                      __("No password saved")
                    }}</span>
                  </div>
                </li>
              </ul>
              <p
                v-if="h.remarks"
                class="border-t border-outline-gray-1 px-4 py-2 text-p-sm text-ink-gray-7"
              >
                {{ h.remarks }}
              </p>
            </li>
          </ul>
        </template>
      </div>
    </div>

    <CredentialsFormDialog
      v-model:open="showForm"
      :project-id="projectId"
      :platforms="data?.platforms ?? []"
      :handover="editing"
      @saved="credentials.reload()"
    />
    <HandBackDialog
      v-model:open="showHandBack"
      :project-id="projectId"
      @done="credentials.reload()"
    />
  </div>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { dateFormat, errorText } from "@/utils";
import { Button, call, createResource, toast } from "frappe-ui";
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideEye from "~icons/lucide/eye";
import LucideEyeOff from "~icons/lucide/eye-off";
import LucideInbox from "~icons/lucide/inbox";
import LucideKeyRound from "~icons/lucide/key-round";
import LucideLock from "~icons/lucide/lock";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideShieldCheck from "~icons/lucide/shield-check";
import LucideUndo2 from "~icons/lucide/undo-2";
import CredentialsFormDialog from "./components/CredentialsFormDialog.vue";
import HandBackDialog from "./components/HandBackDialog.vue";
import ProjectNav from "./components/ProjectNav.vue";
import {
  RETURNED,
  REVEAL_SECONDS,
  type Credential,
  type CredentialHandover,
  type CredentialsData,
} from "./credentialsMeta";

const props = defineProps<{ projectId: string }>();

const credentials = createResource({
  url: "helpdesk.api.client_credentials.get_credentials",
  makeParams: () => ({ project: props.projectId }),
  auto: true,
  onError() {},
});
const data = computed(() => credentials.data as CredentialsData | undefined);
const closed = computed(() =>
  ["Completed", "Cancelled"].includes(data.value?.project_status ?? "")
);
const received = computed(() =>
  (data.value?.handovers ?? []).filter((h) => h.direction !== RETURNED)
);

watch(
  () => props.projectId,
  () => {
    hideAll();
    credentials.reload();
  }
);

const showForm = ref(false);
const editing = ref<CredentialHandover | null>(null);
const showHandBack = ref(false);

function openForm(handover: CredentialHandover | null) {
  editing.value = handover;
  showForm.value = true;
}

// --- showing a password: one at a time on the server, hidden again after a while ---

const shown = reactive<Record<string, string>>({});
const timers: Record<string, ReturnType<typeof setTimeout>> = {};
const revealing = ref("");
const announcement = ref("");

function hide(item: string) {
  delete shown[item];
  clearTimeout(timers[item]);
}

function hideAll() {
  for (const item of Object.keys(shown)) hide(item);
}

async function reveal(handover: string, item: Credential) {
  revealing.value = item.name;
  try {
    const res = await call("helpdesk.api.client_credentials.reveal_password", {
      project: props.projectId,
      handover,
      item: item.name,
    });
    shown[item.name] = res.password;
    timers[item.name] = setTimeout(
      () => hide(item.name),
      REVEAL_SECONDS * 1000
    );
    announcement.value = __(
      "{0} password shown for {1} seconds",
      item.platform,
      String(REVEAL_SECONDS)
    );
  } catch (e) {
    toast.error(errorText(e, __("Couldn't show the password. Try again.")));
  } finally {
    revealing.value = "";
  }
}

onBeforeUnmount(hideAll);

// a client types "facebook.com/brand"; only http(s) addresses become links
function safeUrl(url: string) {
  const full = /^https?:\/\//i.test(url) ? url : `https://${url}`;
  return /^https?:\/\//i.test(full) ? full : "#";
}
</script>
