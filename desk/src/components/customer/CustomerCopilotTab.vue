<template>
  <div class="flex flex-col gap-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h2 class="text-lg-semibold text-ink-gray-9">{{ __("Copilot") }}</h2>
      <Button
        variant="ghost"
        :label="__('Refresh')"
        :loading="setup.loading"
        @click="setup.reload()"
      >
        <template #prefix>
          <LucideRefreshCw class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>

    <div
      v-if="setup.loading && !data"
      class="flex flex-col gap-3"
      :aria-label="__('Loading')"
    >
      <span class="h-12 animate-pulse rounded-lg bg-surface-gray-2" />
      <span class="h-72 animate-pulse rounded-lg bg-surface-gray-2" />
    </div>

    <TaskyState
      v-else-if="setup.error && !data"
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t read this customer\'s Copilot setup')"
      :message="
        errorText(setup.error, __('Check your connection and try again.'))
      "
      error
    >
      <Button :label="__('Retry')" @click="setup.reload()" />
    </TaskyState>

    <template v-else-if="data">
      <p
        v-if="!data.copilot.enabled || data.copilot.shadow"
        role="note"
        class="flex items-start gap-2 rounded-lg bg-info-soft px-3 py-2.5 text-p-sm text-info"
      >
        <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>
          {{ settingsNote }}
        </span>
      </p>

      <div class="grid grid-cols-1 items-start gap-5 lg:grid-cols-2">
        <section
          aria-labelledby="copilot-switches"
          class="flex flex-col gap-5 rounded-lg border border-outline-gray-2 bg-surface-base p-4"
        >
          <div>
            <h3
              id="copilot-switches"
              class="text-base-semibold text-ink-gray-9"
            >
              {{ __("Copilot for {0}", customer) }}
            </h3>
            <p class="mt-0.5 text-p-sm text-ink-gray-5">
              {{
                data.can.switches
                  ? __("Each change saves as you make it.")
                  : __(
                      "Only people who may edit this customer can change these."
                    )
              }}
            </p>
          </div>

          <Switch
            :model-value="data.switches.enabled"
            :label="__('Copilot Enabled')"
            :description="
              __('Every new ticket from {0} starts a Copilot run.', customer)
            "
            :disabled="!data.can.switches || saving.loading"
            @update:model-value="change('enabled', $event)"
          />

          <FormControl
            :model-value="data.switches.level"
            type="select"
            :label="__('Copilot level')"
            :options="levelOptions"
            :disabled="!data.can.switches || saving.loading"
            :description="levelHelp"
            @update:model-value="change('level', $event)"
          />
          <p v-if="data.copilot.shadow" class="-mt-3 text-p-xs text-ink-gray-5">
            {{
              __(
                "Shadow mode is on, so every customer stays at Diagnose only for now."
              )
            }}
          </p>

          <Switch
            :model-value="data.switches.watch"
            :label="__('Watch errors')"
            :description="
              __(
                'Copilot checks {0}\'s sites for new errors and opens a ticket before they report it.',
                customer
              )
            "
            :disabled="!data.can.switches || saving.loading"
            @update:model-value="change('watch', $event)"
          />

          <div class="flex flex-col gap-2 border-t border-outline-gray-1 pt-4">
            <h4 class="text-base-medium text-ink-gray-9">
              {{ __("Who gets Copilot's work") }}
            </h4>
            <dl
              class="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-p-sm"
            >
              <dt class="text-ink-gray-5">{{ __("Developer") }}</dt>
              <dd class="text-ink-gray-8">{{ developersText }}</dd>
              <dt class="text-ink-gray-5">{{ __("Fix Approver") }}</dt>
              <dd class="text-ink-gray-8">
                {{
                  names(data.work_goes_to.fix_approvers) || __("The developers")
                }}
              </dd>
              <dt class="text-ink-gray-5">{{ __("Project Coordinator") }}</dt>
              <dd class="text-ink-gray-8">{{ coordinatorsText }}</dd>
            </dl>
            <p v-if="data.people.rows.length" class="text-p-xs text-ink-gray-5">
              {{
                __(
                  "{0} of this customer's own Copilot People set",
                  data.people.rows.length
                )
              }}
            </p>
            <Button
              v-if="data.can.switches"
              class="self-start"
              :label="__('Edit people')"
              @click="peopleDialog = true"
            >
              <template #prefix>
                <LucideUsers class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
        </section>

        <section
          aria-labelledby="copilot-ready"
          class="rounded-lg border border-outline-gray-2 bg-surface-base p-4"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 id="copilot-ready" class="text-base-semibold text-ink-gray-9">
              {{ __("Ready for Copilot") }}
            </h3>
            <Badge
              :label="
                data.ready.done === data.ready.of
                  ? __('Ready')
                  : __('{0} of {1} ready', data.ready.done, data.ready.of)
              "
              :theme="data.ready.done === data.ready.of ? 'green' : 'orange'"
              size="md"
            />
          </div>
          <p class="mt-0.5 text-p-sm text-ink-gray-5">
            {{ __("In the order you set it up.") }}
          </p>
          <ol role="list" class="mt-2">
            <li
              v-for="check in data.checks"
              :key="check.key"
              class="flex items-start gap-3 border-t border-outline-gray-1 py-3"
            >
              <component
                :is="ICONS[check.state]"
                class="mt-0.5 size-4 shrink-0"
                :class="ICON_CLASS[check.state]"
                aria-hidden="true"
              />
              <div class="min-w-0 flex-1">
                <div class="text-base-medium text-ink-gray-9">
                  {{ check.label }}
                </div>
                <div class="mt-0.5 text-p-sm text-ink-gray-6">
                  {{ check.detail }}
                </div>
              </div>
              <Badge
                :label="__(CHECK_LOOK[check.state].label)"
                :theme="CHECK_LOOK[check.state].badge"
                size="sm"
              />
            </li>
          </ol>
        </section>
      </div>

      <section
        aria-labelledby="copilot-cards"
        class="rounded-lg border border-outline-gray-2 bg-surface-base p-4"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 id="copilot-cards" class="text-base-semibold text-ink-gray-9">
              {{ __("Site cards") }}
            </h3>
            <p class="mt-0.5 text-p-sm text-ink-gray-5">
              {{
                __(
                  "Which site {0}'s tickets are about, and the code it runs.",
                  customer
                )
              }}
            </p>
          </div>
          <Button
            v-if="data.can.add_card"
            variant="solid"
            :label="__('Add site card')"
            @click="openCard('')"
          >
            <template #prefix>
              <LucidePlus class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>

        <div
          v-if="!data.cards.length"
          class="mt-4 rounded-lg border border-dashed border-outline-gray-3 px-4 py-6 text-center"
        >
          <div class="text-base-medium text-ink-gray-9">
            {{ __("No site card yet") }}
          </div>
          <div class="mt-1 text-p-sm text-ink-gray-6">
            {{ emptyCardsText }}
          </div>
        </div>

        <article
          v-for="card in data.cards"
          :key="card.name"
          class="mt-4 flex flex-col gap-3 rounded-lg border border-outline-gray-2 p-4"
          :aria-label="card.site_url || card.name"
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex min-w-0 flex-wrap items-center gap-2">
              <h4 class="truncate text-base-semibold text-ink-gray-9">
                {{ card.site_url || card.name }}
              </h4>
              <Badge :label="__(card.environment)" theme="gray" size="sm" />
              <Badge
                v-if="connectionOf(card)"
                :label="__(connectionOf(card)!.status)"
                :theme="
                  connectionOf(card)!.status === 'Connected' ? 'green' : 'orange'
                "
                size="sm"
              />
              <Badge
                v-else
                :label="__('No connection')"
                theme="red"
                size="sm"
              />
            </div>
            <div v-if="data.can.edit_card" class="flex flex-wrap gap-2">
              <Button
                :label="__('Read apps from the site')"
                :loading="
                  reading.loading && readingCard === card.name + ':site'
                "
                :disabled="!card.connection || reading.loading"
                @click="readApps(card.name, 'site')"
              />
              <Button
                :label="__('Read apps from Press')"
                :loading="
                  reading.loading && readingCard === card.name + ':press'
                "
                :disabled="reading.loading"
                @click="readApps(card.name, 'press')"
              />
              <Button
                variant="subtle"
                :label="__('Edit')"
                @click="openCard(card.name)"
              />
            </div>
          </div>

          <dl
            class="grid grid-cols-1 gap-x-5 gap-y-2 text-p-sm sm:grid-cols-2 xl:grid-cols-4"
          >
            <div>
              <dt class="text-ink-gray-5">{{ __("Connection") }}</dt>
              <dd class="text-ink-gray-8">
                {{ connectionOf(card)?.site_url || card.connection || "-" }}
              </dd>
            </div>
            <div>
              <dt class="text-ink-gray-5">{{ __("Press site") }}</dt>
              <dd class="text-ink-gray-8">
                {{ card.press_site || __("Not filled") }}
              </dd>
            </div>
            <div>
              <dt class="text-ink-gray-5">{{ __("Press release group") }}</dt>
              <dd class="text-ink-gray-8">
                {{ card.press_release_group || __("Not filled") }}
              </dd>
            </div>
            <div>
              <dt class="text-ink-gray-5">{{ __("Shared bench") }}</dt>
              <dd class="text-ink-gray-8">
                {{
                  card.shared_group ? __("Yes, with other customers") : __("No")
                }}
              </dd>
            </div>
          </dl>

          <div>
            <div class="text-p-sm text-ink-gray-5">
              {{
                card.apps_read
                  ? __("Apps, read {0}", card.apps_read)
                  : __("Apps")
              }}
            </div>
            <p v-if="!card.apps.length" class="mt-1 text-p-sm text-ink-gray-8">
              {{ __("Not read yet.") }}
            </p>
            <div v-else class="mt-1 overflow-x-auto">
              <table class="w-full min-w-[28rem] text-p-sm">
                <thead>
                  <tr class="text-left text-ink-gray-5">
                    <th scope="col" class="py-1.5 pr-3 font-medium">
                      {{ __("App") }}
                    </th>
                    <th scope="col" class="px-3 py-1.5 font-medium">
                      {{ __("Branch") }}
                    </th>
                    <th scope="col" class="px-3 py-1.5 font-medium">
                      {{ __("Commit") }}
                    </th>
                    <th scope="col" class="py-1.5 pl-3 font-medium">
                      {{ __("State") }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="app in card.apps"
                    :key="app.app"
                    class="border-t border-outline-gray-1"
                  >
                    <td class="py-1.5 pr-3 text-ink-gray-8">{{ app.app }}</td>
                    <td class="px-3 py-1.5 text-ink-gray-6">
                      {{ app.branch || "-" }}
                    </td>
                    <td class="px-3 py-1.5 font-mono text-ink-gray-6">
                      {{ app.commit || "-" }}
                    </td>
                    <td class="py-1.5 pl-3">
                      <Badge
                        :label="__(app.drift)"
                        :theme="
                          app.drift === 'Drift'
                            ? 'red'
                            : app.drift === 'In sync'
                            ? 'green'
                            : 'gray'
                        "
                        size="sm"
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <p
            v-if="notices[card.name]"
            role="status"
            class="rounded-lg px-3 py-2 text-p-sm"
            :class="
              notices[card.name].ok
                ? 'bg-success-soft text-success'
                : 'bg-warning-soft text-warning'
            "
          >
            {{ notices[card.name].text }}
          </p>
        </article>
      </section>
    </template>

    <CopilotPeopleDialog
      v-if="data"
      v-model="peopleDialog"
      :customer="customer"
      :people="data.people"
      @saved="setup.setData($event)"
    />
    <SiteCardDialog
      v-model="cardDialog"
      :customer="customer"
      :card-name="cardName"
      @saved="setup.setData($event)"
    />
  </div>
</template>

<script setup lang="ts">
import CopilotPeopleDialog from "@/components/copilot/CopilotPeopleDialog.vue";
import SiteCardDialog from "@/components/copilot/SiteCardDialog.vue";
import {
  CHECK_LOOK,
  SETUP_API,
  type CheckState,
  type CopilotSetup,
  type Person,
  type SetupCard,
} from "@/components/copilot/setupMeta";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Badge,
  Button,
  createResource,
  FormControl,
  Switch,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, type Component } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideInfo from "~icons/lucide/info";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideUsers from "~icons/lucide/users";

const props = defineProps<{ customer: string }>();

const ICONS: Record<CheckState, Component> = {
  done: LucideCircleCheck,
  missing: LucideCircleX,
  later: LucideCircleDashed,
};
const ICON_CLASS: Record<CheckState, string> = {
  done: "text-success",
  missing: "text-danger",
  later: "text-ink-gray-4",
};

const setup = createResource({
  url: `${SETUP_API}.customer`,
  makeParams: () => ({ name: props.customer }),
  auto: true,
});
const data = computed(() => setup.data as CopilotSetup | undefined);

const settingsNote = computed(() => {
  const c = data.value?.copilot;
  if (!c) return "";
  if (!c.enabled)
    return __(
      "Copilot is switched off for everyone in HDS Copilot Settings{0}. Nothing runs for {1} until it is switched on there too.",
      c.shadow ? __(", and shadow mode is on") : "",
      props.customer
    );
  return __(
    "Shadow mode is on: Copilot diagnoses for the team only, and customers see nothing from it."
  );
});

const levelOptions = computed(() => [
  {
    label: __(
      "Default ({0})",
      __(data.value?.default_level || "Diagnose only")
    ),
    value: "",
  },
  ...(data.value?.levels || []).map((level) => ({
    label: __(level),
    value: level,
  })),
]);

// what each level allows; each one also allows what the ones before it do
const LEVEL_HELP: Record<string, string> = {
  "Diagnose only": __(
    "Diagnose only: Copilot investigates each new ticket and writes its diagnosis for the team. The customer sees nothing from Copilot."
  ),
  Explain: __(
    "Explain: the customer also sees the stages on their ticket and the explanations agents send."
  ),
  Fix: __(
    "Fix: Copilot also writes code fixes as pull requests. One person approves each, and Press deploys it."
  ),
  "Fix and data": __(
    "Fix and data: a senior may also approve changes to the customer's settings and data, which can be undone."
  ),
};
const levelHelp = computed(() => {
  const d = data.value;
  if (!d) return "";
  return LEVEL_HELP[d.switches.level || d.default_level] || "";
});

function names(people: Person[]): string {
  return people.map((p) => p.name).join(", ");
}

const developersText = computed(() => {
  const w = data.value?.work_goes_to;
  if (!w) return "";
  const who = names(w.developers);
  if (!who)
    return __(
      "Nobody yet: set a Ticket Owner, or a Developer in Copilot People"
    );
  if (w.developers_from === "owner")
    return __("{0} (the Ticket Owner, then the Backup Ticket Owner)", who);
  if (w.developers_from === "common")
    return __("{0} (the common Developers in HDS Copilot Settings)", who);
  return who;
});

const coordinatorsText = computed(() => {
  const w = data.value?.work_goes_to;
  if (!w) return "";
  const who = names(w.coordinators);
  if (!who) return __("None set");
  return w.coordinators_from === "common"
    ? __("{0} (the common ones)", who)
    : who;
});

const emptyCardsText = computed(() => {
  const site = data.value?.connections.find(
    (c) => c.status === "Connected"
  )?.site_url;
  return site
    ? __("Start with the Production site: {0}, the connected site.", site)
    : __("Start with the Production site.");
});

function connectionOf(card: SetupCard) {
  return data.value?.connections.find((c) => c.name === card.connection);
}

// --- the switches ---------------------------------------------------------------------------

const saving = createResource({
  url: `${SETUP_API}.save_switches`,
  onSuccess: (result: CopilotSetup) => {
    setup.setData(result);
    toast.success(__("Saved"));
  },
  onError: (err: unknown) => {
    toast.error(errorText(err, __("Not saved")));
    setup.reload();
  },
});

function change(key: "enabled" | "level" | "watch", value: unknown) {
  saving.submit({
    name: props.customer,
    values: JSON.stringify({ [key]: key === "level" ? value || "" : !!value }),
  });
}

// --- site cards ------------------------------------------------------------------------------

const peopleDialog = ref(false);
const cardDialog = ref(false);
const cardName = ref("");
function openCard(name: string) {
  cardName.value = name;
  cardDialog.value = true;
}

const notices = reactive<Record<string, { ok: boolean; text: string }>>({});
const readingCard = ref("");
const reading = createResource({
  url: `${SETUP_API}.read_apps`,
});

function readApps(name: string, source: "site" | "press") {
  readingCard.value = `${name}:${source}`;
  delete notices[name];
  reading.submit(
    { name, source },
    {
      onSuccess: (r: {
        result: { apps?: number; drift?: string[] };
        setup: CopilotSetup;
      }) => {
        setup.setData(r.setup);
        const apps = r.result?.apps || 0;
        const drift = r.result?.drift || [];
        notices[name] = {
          ok: !drift.length,
          text: drift.length
            ? __(
                "{0} apps read; changed on the site: {1}",
                apps,
                drift.join(", ")
              )
            : source === "site"
            ? __("{0} apps read from the site just now.", apps)
            : __("{0} apps read from Press just now.", apps),
        };
      },
      onError: (err: unknown) => {
        notices[name] = {
          ok: false,
          text: errorText(err, __("The apps could not be read.")),
        };
      },
    }
  );
}
</script>
