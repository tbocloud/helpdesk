<template>
  <Dialog v-model:open="show" :title="title">
    <template #default>
      <div class="flex flex-col gap-4">
        <RecordCombobox
          v-if="!customer"
          v-model="chosen"
          doctype="HD Customer"
          :label="__('Customer')"
          :placeholder="__('Choose the customer')"
        />
        <div v-else>
          <div class="text-p-sm text-ink-gray-5">{{ __("Customer") }}</div>
          <div class="text-base-medium text-ink-gray-9">{{ customer }}</div>
        </div>

        <div
          v-if="forCustomer && !ready && !problem"
          class="h-48 animate-pulse rounded-lg bg-surface-gray-2"
          :aria-label="__('Loading')"
        />

        <template v-else-if="current">
          <fieldset class="flex flex-col gap-1.5">
            <legend class="mb-1.5 text-p-sm text-ink-gray-5">
              {{ __("Environment") }}
            </legend>
            <TabButtons
              v-model="form.environment"
              :options="environments"
              :aria-label="__('Environment')"
            />
            <p class="text-p-xs text-ink-gray-5">
              {{
                __(
                  "A customer has one Production site: its tickets are about that one. A fix is tried on UAT first."
                )
              }}
            </p>
          </fieldset>

          <FormControl
            v-if="connectionOptions.length"
            v-model="form.connection"
            type="select"
            :label="__('Connection')"
            :options="connectionOptions"
            :description="
              connectionOptions.length === 1
                ? __('The customer\'s one connection, already chosen.')
                : __('Pick the site\'s connection: its address fills in.')
            "
          />
          <p v-else class="text-p-sm text-ink-gray-6">
            {{
              __(
                "This customer has no connection yet, so Copilot cannot read the site. You can still save the card."
              )
            }}
          </p>

          <FormControl
            v-model="form.site_url"
            type="text"
            :label="__('Site URL')"
            placeholder="https://erp.example.com"
          />

          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormControl
              v-model="form.press_site"
              type="text"
              :label="__('Press site')"
              :description="__('The site\'s name in Press.')"
            />
            <FormControl
              v-model="form.press_release_group"
              type="text"
              :label="__('Press release group')"
              placeholder="bench-…"
              :description="
                __(
                  'DevOps knows it. Needed for fixes and Read apps from Press.'
                )
              "
            />
          </div>

          <FormControl
            v-model="form.shared_group"
            type="checkbox"
            :label="
              __(
                'Shared release group: other customers\' sites move with this bench\'s deploys'
              )
            "
          />

          <p
            v-if="!editing"
            class="rounded-lg bg-surface-gray-1 px-3 py-2 text-p-sm text-ink-gray-6"
          >
            {{
              __(
                "After saving, use Read apps on the card: it fills each app's repository, branch and commit, so Copilot reads the code the customer runs."
              )
            }}
          </p>
        </template>

        <ErrorMessage v-if="problem" :message="problem" />
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="show = false" />
        <Button
          variant="solid"
          :label="__('Save site card')"
          :loading="savingFor === opening"
          :disabled="!current"
          @click="submit"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  Dialog,
  ErrorMessage,
  FormControl,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import {
  SETUP_API,
  type CopilotSetup,
  type SetupCard,
  type SetupConnection,
} from "./setupMeta";
import RecordCombobox from "./RecordCombobox.vue";

const props = defineProps<{
  /** the customer the card is for; empty: the person chooses one */
  customer?: string;
  /** the card to change; empty: a new card */
  cardName?: string;
}>();
// "saved": the customer changed on the server; the page reads it again
const emit = defineEmits<{ saved: [] }>();
const show = defineModel<boolean>({ default: false });

const chosen = ref("");
const forCustomer = computed(() => props.customer || chosen.value);
const editing = computed(() => !!props.cardName);
const title = computed(() =>
  editing.value ? __("Edit site card") : __("Add site card")
);
const environments = [
  { label: __("Production"), value: "Production" },
  { label: __("UAT"), value: "UAT" },
  { label: __("Sandbox"), value: "Sandbox" },
];

const form = reactive({
  environment: "Production",
  connection: "",
  site_url: "",
  press_site: "",
  press_release_group: "",
  shared_group: false,
});
const problem = ref("");

// Each opening reads the customer afresh, and only the read of the current opening fills the
// form: a slower read from an earlier opening (another card, or another customer) is ignored,
// so its values can never be saved onto this card (review of #351). Until this opening's read
// has filled the form, nothing is shown and Save stays off.
const opening = ref(0);
const loaded = ref<CopilotSetup | null>(null);
const ready = computed(() => !!loaded.value);

async function load(customer: string, mine: number) {
  try {
    const data = (await call(`${SETUP_API}.customer`, {
      name: customer,
    })) as CopilotSetup;
    if (mine !== opening.value) return;
    fill(data);
    loaded.value = data;
  } catch (err) {
    if (mine !== opening.value) return;
    problem.value = errorText(err, __("Couldn't read the customer"));
  }
}

const current = computed(() =>
  forCustomer.value ? loaded.value ?? undefined : undefined
);
const connections = computed<SetupConnection[]>(
  () => current.value?.connections ?? []
);
const connectionOptions = computed(() =>
  connections.value.map((c) => ({
    label: `${c.site_url || c.name} · ${__(c.status)}`,
    value: c.name,
  }))
);

function fill(data: CopilotSetup) {
  const card: SetupCard | undefined = props.cardName
    ? data.cards.find((c) => c.name === props.cardName)
    : undefined;
  if (card) {
    Object.assign(form, {
      environment: card.environment,
      connection: card.connection,
      site_url: card.site_url,
      press_site: card.press_site,
      press_release_group: card.press_release_group,
      shared_group: card.shared_group,
    });
    return;
  }
  const first =
    data.connections.find((c) => c.status === "Connected") ||
    data.connections[0];
  const hasProduction = data.cards.some((c) => c.environment === "Production");
  Object.assign(form, {
    environment: hasProduction ? "UAT" : "Production",
    connection: first?.name ?? "",
    site_url: first?.site_url ?? "",
    press_site: "",
    press_release_group: "",
    shared_group: false,
  });
}

// a new connection's address fills the URL, unless the person typed another
watch(
  () => form.connection,
  (name, before) => {
    const now = connections.value.find((c) => c.name === name);
    const was = connections.value.find((c) => c.name === before);
    if (now && (!form.site_url || form.site_url === was?.site_url)) {
      form.site_url = now.site_url;
    }
  }
);

watch(
  [show, forCustomer, () => props.cardName],
  ([open, customer]) => {
    // a new opening (or a closed dialog) makes every earlier read stale
    opening.value += 1;
    problem.value = "";
    loaded.value = null;
    if (open && customer) load(customer, opening.value);
  },
  { immediate: true }
);

// A save belongs to the opening that started it: if the dialog was closed and opened again
// (another card) before the save answered, that answer neither closes nor marks the new one
// (review of #351). The saved card still reaches the page, which shows the newer state.
const savingFor = ref<number | null>(null);

async function submit() {
  const mine = opening.value;
  problem.value = "";
  const values: Record<string, unknown> = {
    environment: form.environment,
    connection: form.connection || null,
    site_url: form.site_url,
    press_site: form.press_site,
    press_release_group: form.press_release_group,
    shared_group: form.shared_group ? 1 : 0,
  };
  if (!editing.value) values.customer_name = forCustomer.value;
  savingFor.value = mine;
  try {
    await call(`${SETUP_API}.save_site_card`, {
      values: JSON.stringify(values),
      name: props.cardName || undefined,
    });
    toast.success(__("Site card saved"));
    emit("saved");
    if (mine === opening.value) show.value = false;
  } catch (err) {
    if (mine === opening.value) {
      problem.value = errorText(err, __("The site card was not saved"));
    }
  } finally {
    if (savingFor.value === mine) savingFor.value = null;
  }
}
</script>
