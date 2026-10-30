<template>
  <div class="flex h-full flex-col">
    <ProjectNav :project-id="projectId">
      <template #actions>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="connection.loading && !!connection.data"
          @click="connection.reload()"
        >
          <template #icon><LucideRefreshCw class="size-4" /></template>
        </Button>
      </template>
    </ProjectNav>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-3xl px-4 py-5 md:px-6">
        <TaskyState
          v-if="connection.error && !connection.data"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the Meta connection')"
          :message="
            errorText(
              connection.error,
              __('Check your connection and try again.')
            )
          "
        >
          <Button :label="__('Retry')" @click="connection.reload()" />
        </TaskyState>

        <div
          v-else-if="!data"
          class="h-40 animate-pulse rounded-xl bg-surface-gray-1"
          aria-busy="true"
        />

        <template v-else>
          <h2 class="mb-1 text-lg-semibold text-ink-gray-9">
            {{ __("Facebook and Instagram") }}
          </h2>
          <p class="mb-4 max-w-prose text-p-sm text-ink-gray-6">
            {{
              __(
                "Connect the client's Facebook Page (and the Instagram account linked to it) to publish their approved posts straight from the content calendar. You must be an admin of the Page."
              )
            }}
          </p>

          <p
            v-if="flashError"
            role="alert"
            class="mb-4 flex items-start gap-2 rounded-lg bg-danger-soft px-3 py-2 text-p-sm text-danger"
          >
            <LucideCircleAlert
              class="mt-0.5 size-4 shrink-0"
              aria-hidden="true"
            />
            {{ flashError }}
          </p>

          <TaskyState
            v-if="!data.enabled"
            :icon="LucidePlugZap"
            :title="__('Meta isn\'t set up yet')"
            :message="
              __(
                'A System Manager adds the Meta app in Settings → Meta, then you can connect this client.'
              )
            "
          />

          <section
            v-else-if="!conn"
            class="flex flex-col items-start gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
          >
            <p class="text-p-sm text-ink-gray-7">
              {{
                __(
                  "Not connected. Facebook asks the Page admin to allow posting; the hub then keeps a Page token, encrypted, and never shows it."
                )
              }}
            </p>
            <Button
              variant="solid"
              :label="__('Connect Meta')"
              :loading="starting"
              @click="startConnect"
            >
              <template #prefix>
                <LucideLink class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </section>

          <section
            v-else-if="conn.status === 'Pending'"
            class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
          >
            <h3 class="text-base-medium text-ink-gray-9">
              {{ __("Pick the Page to publish to") }}
            </h3>
            <div
              v-if="pages.loading"
              class="h-16 animate-pulse rounded-lg bg-surface-gray-1"
              aria-busy="true"
            />
            <p
              v-else-if="pages.error"
              role="alert"
              class="text-p-sm text-danger"
            >
              {{ errorText(pages.error, __("Couldn't load the Pages.")) }}
              <Button
                variant="ghost"
                :label="__('Try again')"
                @click="pages.reload()"
              />
            </p>
            <p
              v-else-if="!pages.data?.length"
              class="text-p-sm text-ink-gray-7"
            >
              {{
                __(
                  "This Facebook account has no Page it can post to. Ask the client to make you a Page admin, then connect again."
                )
              }}
            </p>
            <fieldset v-else class="flex flex-col gap-2">
              <legend class="sr-only">{{ __("Pages") }}</legend>
              <label
                v-for="page in pages.data"
                :key="page.id"
                class="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-outline-gray-2 px-3 py-2 has-[:checked]:border-brand has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-highlight"
              >
                <input
                  v-model="chosen"
                  type="radio"
                  name="page"
                  :value="page.id"
                  class="accent-brand"
                />
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-base text-ink-gray-9">{{
                    page.name
                  }}</span>
                  <span class="block text-p-sm text-ink-gray-6">
                    {{
                      page.instagram_username
                        ? __("Instagram: @{0}", page.instagram_username)
                        : __("No Instagram account linked")
                    }}
                  </span>
                </span>
              </label>
            </fieldset>
            <div class="flex flex-wrap justify-end gap-2">
              <Button :label="__('Cancel')" @click="disconnect" />
              <Button
                variant="solid"
                :label="__('Use this Page')"
                :disabled="!chosen"
                :loading="selecting"
                @click="selectPage"
              />
            </div>
          </section>

          <section
            v-else
            class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
          >
            <div class="flex flex-wrap items-center gap-2">
              <TaskyBadge
                v-if="conn.status === 'Connected'"
                tone="success"
                :icon="LucideCircleCheck"
                :label="__('Connected')"
              />
              <TaskyBadge
                v-else
                tone="danger"
                :icon="LucideCircleAlert"
                :label="
                  conn.status === 'Expired'
                    ? __('Expired')
                    : __('Needs attention')
                "
              />
              <span class="min-w-0 truncate text-base-medium text-ink-gray-9">
                {{ conn.facebook_page_name }}
              </span>
            </div>
            <dl
              class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-p-sm"
            >
              <dt class="text-ink-gray-6">{{ __("Instagram") }}</dt>
              <dd class="text-ink-gray-8">
                {{
                  conn.instagram_username
                    ? `@${conn.instagram_username}`
                    : __("No account linked to this Page")
                }}
              </dd>
              <dt class="text-ink-gray-6">{{ __("Connected by") }}</dt>
              <dd class="text-ink-gray-8">
                {{ conn.connected_by }}
                <template v-if="conn.connected_on">
                  · {{ dateFormat(conn.connected_on, "D MMM YYYY") }}
                </template>
              </dd>
            </dl>
            <p
              v-if="conn.last_error"
              role="alert"
              class="text-p-sm text-danger"
            >
              {{ conn.last_error }}
            </p>
            <div class="flex flex-wrap justify-end gap-2">
              <Button
                :variant="conn.status === 'Connected' ? 'subtle' : 'solid'"
                :label="__('Connect again')"
                :loading="starting"
                @click="startConnect"
              />
              <Button
                theme="red"
                :label="__('Disconnect')"
                @click="confirmDisconnect = true"
              />
            </div>
          </section>
        </template>
      </div>
    </div>

    <Dialog
      v-model="confirmDisconnect"
      :options="{ title: __('Disconnect Meta?'), size: 'sm' }"
    >
      <template #body-content>
        <p class="text-p-sm text-ink-gray-7">
          {{
            __(
              "The saved Page token is deleted. Posts already scheduled for Facebook or Instagram will fail until Meta is connected again."
            )
          }}
        </p>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button
            :label="__('Keep connected')"
            @click="confirmDisconnect = false"
          />
          <Button
            theme="red"
            variant="solid"
            :label="__('Disconnect Meta')"
            @click="disconnect"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { dateFormat, errorText } from "@/utils";
import { Button, call, createResource, Dialog, toast } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideLink from "~icons/lucide/link";
import LucidePlugZap from "~icons/lucide/plug-zap";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import ProjectNav from "./components/ProjectNav.vue";

interface Connection {
  status: "Pending" | "Connected" | "Expired" | "Error";
  last_error?: string | null;
  facebook_page_name?: string | null;
  instagram_username?: string | null;
  connected_by?: string | null;
  connected_on?: string | null;
}
interface MetaPage {
  id: string;
  name: string;
  instagram_username?: string | null;
}

const props = defineProps<{ projectId: string }>();
const route = useRoute();
const router = useRouter();

// Facebook sends the person back here with ?error=… when sign-in failed
const flashError = ref(String(route.query.error || ""));
if (route.query.error || route.query.signed_in) router.replace({ query: {} });

const connection = createResource({
  url: "helpdesk.api.meta.get_connection",
  makeParams: () => ({ project: props.projectId }),
  auto: true,
});
const data = computed(
  () =>
    connection.data as
      | { enabled: boolean; connection: Connection | null }
      | undefined
);
const conn = computed(() => data.value?.connection ?? null);

const pages = createResource({
  url: "helpdesk.api.meta.list_pages",
  makeParams: () => ({ project: props.projectId }),
});
const chosen = ref("");
watch(
  () => conn.value?.status,
  (status) => {
    if (status === "Pending") pages.reload();
  },
  { immediate: true }
);

const starting = ref(false);
async function startConnect() {
  starting.value = true;
  try {
    const { url } = await call("helpdesk.api.meta.start_connect", {
      project: props.projectId,
    });
    window.location.href = url;
  } catch (e) {
    toast.error(errorText(e, __("Couldn't start the Facebook sign-in.")));
    starting.value = false;
  }
}

const selecting = ref(false);
async function selectPage() {
  selecting.value = true;
  try {
    await call("helpdesk.api.meta.select_page", {
      project: props.projectId,
      page_id: chosen.value,
    });
    await connection.reload();
    toast.success(__("Meta connected"));
  } catch (e) {
    toast.error(errorText(e, __("Couldn't connect that Page.")));
  } finally {
    selecting.value = false;
  }
}

const confirmDisconnect = ref(false);
async function disconnect() {
  try {
    await call("helpdesk.api.meta.disconnect", { project: props.projectId });
    confirmDisconnect.value = false;
    await connection.reload();
    toast.success(__("Meta disconnected"));
  } catch (e) {
    toast.error(errorText(e, __("Couldn't disconnect.")));
  }
}
</script>
