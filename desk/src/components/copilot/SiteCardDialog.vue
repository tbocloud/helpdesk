<template>
  <Dialog v-model:open="show" :title="title">
    <template #default>
      <div class="flex flex-col gap-4">
        <Link
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
          :loading="save.loading"
          :disabled="!current || setup.loading"
          @click="submit"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { Link } from "@/components";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
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

const props = defineProps<{
  /** the customer the card is for; empty: the person chooses one */
  customer?: string;
  /** the card to change; empty: a new card */
  cardName?: string;
}>();
const emit = defineEmits<{ saved: [setup: CopilotSetup] }>();
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

const setup = createResource({
  url: `${SETUP_API}.customer`,
  makeParams: () => ({ name: forCustomer.value }),
  onSuccess: (data: CopilotSetup) => fill(data),
  onError: (err: unknown) => {
    problem.value = errorText(err, __("Couldn't read the customer"));
  },
});
// true once the form holds this opening's values: until then the last card's values may still
// be in it, so nothing is shown or saved (review of #351)
const ready = ref(false);
const current = computed(() =>
  forCustomer.value && ready.value
    ? (setup.data as CopilotSetup | undefined)
    : undefined
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
  ready.value = true;
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
  [show, forCustomer],
  ([open, customer]) => {
    problem.value = "";
    ready.value = false;
    if (open && customer) setup.reload();
  },
  { immediate: true }
);

const save = createResource({
  url: `${SETUP_API}.save_site_card`,
  onSuccess: (data: CopilotSetup) => {
    toast.success(__("Site card saved"));
    emit("saved", data);
    show.value = false;
  },
  onError: (err: unknown) => {
    problem.value = errorText(err, __("The site card was not saved"));
  },
});

function submit() {
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
  save.submit({
    values: JSON.stringify(values),
    name: props.cardName || undefined,
  });
}
</script>
