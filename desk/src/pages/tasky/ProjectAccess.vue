<template>
  <div class="flex h-full flex-col">
    <ProjectNav :project-id="projectId">
      <template #actions>
        <Button
          size="md"
          :label="__('Refresh')"
          :loading="access.loading && !!access.data"
          @click="access.reload()"
        >
          <template #icon
            ><LucideRefreshCw class="size-[18px]" aria-hidden="true"
          /></template>
        </Button>
      </template>
    </ProjectNav>

    <div class="relative flex-1 overflow-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <p class="sr-only" aria-live="polite">{{ announcement }}</p>
        <TaskyState
          v-if="access.error && !access.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the access details')"
          :message="
            errorText(access.error, __('Check your connection and try again.'))
          "
        >
          <Button :label="__('Retry')" @click="access.reload()" />
        </TaskyState>

        <div v-else-if="!data" class="flex flex-col gap-4" aria-busy="true">
          <div
            v-for="i in 2"
            :key="i"
            class="h-28 animate-pulse rounded-xl bg-surface-gray-3"
          />
        </div>

        <template v-else>
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="text-base font-semibold text-ink-gray-9">
              {{ __("Access and handover") }}
            </h2>
            <Button
              v-if="data.can_handle"
              class="ml-auto"
              variant="solid"
              size="md"
              :label="__('Add an entry')"
              @click="openForm(null)"
            >
              <template #prefix>
                <LucidePlus class="size-[18px]" aria-hidden="true" />
              </template>
            </Button>
          </div>

          <p
            class="-mt-2 flex items-start gap-2 text-p-sm text-ink-gray-6"
            role="note"
          >
            <LucideShieldCheck
              class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
            {{
              data.can_handle
                ? __(
                    "Repositories, URLs, servers and logins this project runs on. Passwords stay hidden; showing one is written to the project's timeline with your name."
                  )
                : __(
                    "Repositories, URLs, servers and logins this project runs on. Passwords are shown only to the project's managers and developers."
                  )
            }}
          </p>

          <TaskyState
            v-if="!data.entries.length"
            class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
            :icon="LucideServer"
            :title="__('Nothing recorded yet')"
            :message="
              __(
                'Add the Git repository, the backend and frontend URLs, the app, the server and the demo login, so anyone can pick this project up later.'
              )
            "
          >
            <Button
              v-if="data.can_handle"
              variant="solid"
              :label="__('Add an entry')"
              @click="openForm(null)"
            />
          </TaskyState>

          <template v-else>
            <section
              v-for="group in groups"
              :key="group.kind"
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
              :aria-labelledby="`access-${group.slug}`"
            >
              <h3
                :id="`access-${group.slug}`"
                class="flex items-center gap-2 border-b border-outline-gray-2 px-4 py-3 text-[13px] font-semibold text-ink-gray-9"
              >
                <component
                  :is="kindIcon(group.kind)"
                  class="size-4 text-ink-gray-6"
                  aria-hidden="true"
                />
                {{ __(group.kind) }}
                <span class="font-normal tabular-nums text-ink-gray-5">{{
                  group.entries.length
                }}</span>
              </h3>
              <ul role="list">
                <li
                  v-for="item in group.entries"
                  :key="item.name"
                  class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
                >
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="text-[13px] font-semibold text-ink-gray-9">{{
                      item.label
                    }}</span>
                    <TaskyBadge
                      v-if="item.environment"
                      :label="__(item.environment)"
                    />
                    <div v-if="data.can_handle" class="ml-auto flex gap-1">
                      <Button
                        variant="ghost"
                        :aria-label="__('Edit {0}', item.label)"
                        @click="openForm(item)"
                      >
                        <template #icon>
                          <LucidePencil class="size-4" aria-hidden="true" />
                        </template>
                      </Button>
                      <Button
                        variant="ghost"
                        theme="red"
                        :aria-label="__('Remove {0}', item.label)"
                        @click="removing = item"
                      >
                        <template #icon>
                          <LucideTrash2 class="size-4" aria-hidden="true" />
                        </template>
                      </Button>
                    </div>
                  </div>

                  <dl
                    class="grid grid-cols-1 gap-x-6 gap-y-2 text-sm md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]"
                  >
                    <div
                      v-if="item.url"
                      class="flex min-w-0 items-center gap-1"
                    >
                      <dt class="sr-only">{{ __("URL") }}</dt>
                      <dd class="min-w-0 truncate">
                        <a
                          v-if="safeUrl(item.url)"
                          :href="safeUrl(item.url) ?? undefined"
                          target="_blank"
                          rel="noopener noreferrer"
                          class="rounded font-mono text-xs text-brand-ink underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                          >{{ item.url }}</a
                        >
                        <span
                          v-else
                          class="font-mono text-xs text-ink-gray-8"
                          >{{ item.url }}</span
                        >
                      </dd>
                      <CopyButton :value="item.url" :what="__('URL')" />
                    </div>
                    <div
                      v-if="item.username"
                      class="flex min-w-0 items-center gap-1"
                    >
                      <dt class="text-xs text-ink-gray-5">{{ __("User") }}</dt>
                      <dd
                        class="min-w-0 truncate font-mono text-xs text-ink-gray-8"
                      >
                        {{ item.username }}
                      </dd>
                      <CopyButton
                        :value="item.username"
                        :what="__('Username')"
                      />
                    </div>
                    <div
                      v-if="item.has_password"
                      class="flex min-w-0 items-center gap-1"
                    >
                      <dt class="text-xs text-ink-gray-5">
                        {{ __("Password") }}
                      </dt>
                      <dd
                        class="min-w-0 truncate font-mono text-xs text-ink-gray-8"
                        :aria-label="
                          shown[item.name] ? __('Password') : __('Hidden')
                        "
                      >
                        {{ shown[item.name] ?? "••••••••" }}
                      </dd>
                      <template v-if="data.can_handle">
                        <template v-if="shown[item.name]">
                          <CopyButton
                            :value="shown[item.name]"
                            :what="__('Password')"
                          />
                          <Button
                            variant="ghost"
                            :aria-label="__('Hide')"
                            @click="hide(item.name)"
                          >
                            <template #icon>
                              <LucideEyeOff class="size-4" aria-hidden="true" />
                            </template>
                          </Button>
                        </template>
                        <Button
                          v-else
                          variant="ghost"
                          :aria-label="
                            __('Show the password of {0}', item.label)
                          "
                          :loading="revealing === item.name"
                          @click="reveal(item)"
                        >
                          <template #icon>
                            <LucideEye class="size-4" aria-hidden="true" />
                          </template>
                        </Button>
                      </template>
                    </div>
                  </dl>

                  <p
                    v-if="item.notes"
                    class="whitespace-pre-line text-p-sm text-ink-gray-7"
                  >
                    {{ item.notes }}
                  </p>
                  <p v-if="item.added_by_name" class="text-xs text-ink-gray-5">
                    {{ __("Added by {0}", item.added_by_name) }}
                  </p>
                </li>
              </ul>
            </section>
          </template>
        </template>
      </div>
    </div>

    <AccessEntryDialog
      v-model:open="showForm"
      :project-id="projectId"
      :kinds="data?.kinds ?? []"
      :environments="data?.environments ?? []"
      :entry="editing"
      @saved="access.reload()"
    />
    <Dialog
      :open="!!removing"
      :options="{
        title: __('Remove {0}?', removing?.label ?? ''),
        message: __(
          'Its link, login and password are deleted. The project\'s timeline keeps a line saying you removed it.'
        ),
      }"
      @update:open="(value: boolean) => !value && (removing = null)"
    >
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="removing = null" />
          <Button
            variant="solid"
            theme="red"
            :label="__('Remove')"
            :loading="deleting"
            @click="remove()"
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
import { errorText } from "@/utils";
import { Button, Dialog, call, createResource, toast } from "frappe-ui";
import {
  computed,
  defineComponent,
  h,
  onBeforeUnmount,
  reactive,
  ref,
  watch,
  type Component,
} from "vue";
import LucideAppWindow from "~icons/lucide/app-window";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCopy from "~icons/lucide/copy";
import LucideDatabase from "~icons/lucide/database";
import LucideEye from "~icons/lucide/eye";
import LucideEyeOff from "~icons/lucide/eye-off";
import LucideGitBranch from "~icons/lucide/git-branch";
import LucideGlobe from "~icons/lucide/globe";
import LucideKeyRound from "~icons/lucide/key-round";
import LucidePencil from "~icons/lucide/pencil";
import LucidePlug from "~icons/lucide/plug";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideServer from "~icons/lucide/server";
import LucideShieldCheck from "~icons/lucide/shield-check";
import LucideSmartphone from "~icons/lucide/smartphone";
import LucideTrash2 from "~icons/lucide/trash-2";
import AccessEntryDialog from "./components/AccessEntryDialog.vue";
import ProjectNav from "./components/ProjectNav.vue";
import {
  REVEAL_SECONDS,
  safeUrl,
  type AccessEntry,
  type ProjectAccessData,
} from "./projectAccessMeta";

const props = defineProps<{ projectId: string }>();

const access = createResource({
  url: "helpdesk.api.project_access.get_project_access",
  makeParams: () => ({ project: props.projectId }),
  auto: true,
  onError() {},
});
const data = computed(() => access.data as ProjectAccessData | undefined);

// entries come sorted by kind; one card per kind
const groups = computed(() => {
  const byKind = new Map<string, AccessEntry[]>();
  for (const entry of data.value?.entries ?? []) {
    byKind.set(entry.kind, [...(byKind.get(entry.kind) ?? []), entry]);
  }
  return [...byKind].map(([kind, entries]) => ({
    kind,
    slug: kind.toLowerCase().replace(/[^a-z]+/g, "-"),
    entries,
  }));
});

const KIND_ICONS: Record<string, Component> = {
  "Git repository": LucideGitBranch,
  "Backend / ERP site": LucideServer,
  "Frontend / website": LucideGlobe,
  "Mobile app": LucideSmartphone,
  "Server / hosting": LucideServer,
  Database: LucideDatabase,
  "API / integration": LucidePlug,
  Login: LucideKeyRound,
};
function kindIcon(kind: string) {
  return KIND_ICONS[kind] ?? LucideAppWindow;
}

watch(
  () => props.projectId,
  () => {
    hideAll();
    access.reload();
  }
);

const showForm = ref(false);
const editing = ref<AccessEntry | null>(null);
function openForm(entry: AccessEntry | null) {
  editing.value = entry;
  showForm.value = true;
}

const removing = ref<AccessEntry | null>(null);
const deleting = ref(false);
async function remove() {
  if (!removing.value) return;
  deleting.value = true;
  try {
    await call("helpdesk.api.project_access.delete_access_entry", {
      project: props.projectId,
      name: removing.value.name,
    });
    toast.success(__("Removed"));
    removing.value = null;
    access.reload();
  } catch (e) {
    toast.error(errorText(e, __("Couldn't remove it. Try again.")));
  } finally {
    deleting.value = false;
  }
}

// --- showing a password: one at a time from the server, hidden again after a while ---

const shown = reactive<Record<string, string>>({});
const timers: Record<string, ReturnType<typeof setTimeout>> = {};
const revealing = ref("");
const announcement = ref("");

function hide(name: string) {
  delete shown[name];
  clearTimeout(timers[name]);
}
function hideAll() {
  for (const name of Object.keys(shown)) hide(name);
}

async function reveal(item: AccessEntry) {
  revealing.value = item.name;
  try {
    const res = await call(
      "helpdesk.api.project_access.reveal_access_password",
      {
        project: props.projectId,
        name: item.name,
      }
    );
    shown[item.name] = res.password;
    timers[item.name] = setTimeout(
      () => hide(item.name),
      REVEAL_SECONDS * 1000
    );
    announcement.value = __(
      "Password of {0} shown for {1} seconds",
      item.label,
      String(REVEAL_SECONDS)
    );
  } catch (e) {
    toast.error(errorText(e, __("Couldn't show the password. Try again.")));
  } finally {
    revealing.value = "";
  }
}

onBeforeUnmount(hideAll);

// a small "copy" button; says what was copied
const CopyButton = defineComponent({
  props: { value: { type: String, required: true }, what: String },
  setup(p) {
    async function copy() {
      try {
        await navigator.clipboard.writeText(p.value);
        toast.success(__("{0} copied", p.what ?? __("Value")));
      } catch {
        toast.error(__("Couldn't copy. Select it and copy by hand."));
      }
    }
    return () =>
      h(
        Button,
        {
          variant: "ghost",
          "aria-label": __("Copy {0}", p.what ?? ""),
          onClick: copy,
        },
        {
          icon: () => h(LucideCopy, { class: "size-4", "aria-hidden": "true" }),
        }
      );
  },
});
</script>
