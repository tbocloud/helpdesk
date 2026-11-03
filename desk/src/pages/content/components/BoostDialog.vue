<template>
  <Dialog
    v-model="open"
    :options="{ title: __('Boost this post'), size: 'lg' }"
  >
    <template #body-content>
      <div
        v-if="defaults.loading && !form"
        aria-busy="true"
        class="h-40 animate-pulse rounded-lg bg-surface-gray-1"
      />
      <p
        v-else-if="defaults.error && !form"
        role="alert"
        class="flex flex-wrap items-center gap-2 text-p-sm text-danger"
      >
        <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
        {{ errorText(defaults.error, __("Couldn't open the boost form.")) }}
        <Button
          variant="ghost"
          :label="__('Try again')"
          @click="defaults.reload()"
        />
      </p>

      <form
        v-else-if="form"
        id="boost-form"
        class="flex flex-col gap-5"
        @submit.prevent="submit"
      >
        <fieldset v-if="targets.length > 1" class="flex flex-col gap-2">
          <legend class="mb-1 text-xs text-ink-gray-5">
            {{ __("Boost it on") }}
          </legend>
          <TabButtons
            v-model="form.target"
            :aria-label="__('Boost it on')"
            :options="targets.map((t) => ({ label: __(t), value: t }))"
          />
        </fieldset>

        <fieldset class="flex flex-col gap-2">
          <legend class="mb-1 text-xs text-ink-gray-5">
            {{ __("What do you want?") }}
          </legend>
          <label
            v-for="goal in goals"
            :key="goal"
            class="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border border-outline-gray-2 px-3 py-2 has-[:checked]:border-brand has-[:checked]:bg-brand-soft has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-highlight"
          >
            <input
              v-model="form.goal"
              type="radio"
              name="boost-goal"
              :value="goal"
              class="mt-1 accent-brand"
            />
            <span class="min-w-0">
              <span class="block text-base text-ink-gray-9">{{
                __(goal)
              }}</span>
              <span class="block text-p-sm text-ink-gray-6">{{
                __(GOAL_HINTS[goal])
              }}</span>
            </span>
          </label>
        </fieldset>

        <fieldset class="flex flex-col gap-3">
          <legend class="mb-1 text-xs text-ink-gray-5">
            {{ __("Budget") }}
          </legend>
          <TabButtons
            v-model="form.budget_type"
            :aria-label="__('Budget type')"
            :options="[
              { label: __('Per day'), value: 'Per day' },
              { label: __('Total'), value: 'Total' },
            ]"
          />
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <FormControl
              v-model="form.budget_amount"
              type="number"
              :label="
                __(
                  form.budget_type === 'Per day'
                    ? 'Per day ({0})'
                    : 'Total ({0})',
                  currency
                )
              "
              :min="1"
              inputmode="decimal"
              required
            />
            <FormControl
              v-model="form.start_date"
              type="date"
              :label="__('Starts')"
              required
            />
            <FormControl
              v-model="form.end_date"
              type="date"
              :label="__('Ends')"
              required
            />
          </div>
        </fieldset>

        <details
          class="rounded-lg border border-outline-gray-2"
          :open="audienceOpen"
        >
          <summary
            class="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-base text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          >
            <LucideUsers
              class="size-4 shrink-0 text-ink-gray-6"
              aria-hidden="true"
            />
            <span class="min-w-0 flex-1 truncate">
              {{ __("Who sees it") }}: {{ where }},
              {{ form.audience.age_min }}–{{ form.audience.age_max }}
            </span>
            <span class="text-p-sm text-brand-ink">{{ __("Change") }}</span>
          </summary>
          <div class="flex flex-col gap-4 border-t border-outline-gray-2 p-3">
            <div class="flex flex-col gap-2">
              <span class="text-xs text-ink-gray-5">{{ __("Places") }}</span>
              <ul class="flex flex-wrap gap-2" role="list">
                <li
                  v-for="(place, i) in form.audience.locations"
                  :key="place.key"
                >
                  <span
                    class="inline-flex min-h-8 items-center gap-1 rounded-md bg-surface-gray-2 ps-2 text-sm text-ink-gray-8"
                  >
                    {{ place.name }}
                    <button
                      type="button"
                      class="flex size-8 items-center justify-center rounded-md text-ink-gray-6 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                      :aria-label="__('Remove {0}', place.name)"
                      :disabled="form.audience.locations.length === 1"
                      @click="form.audience.locations.splice(i, 1)"
                    >
                      <LucideX class="size-3.5" aria-hidden="true" />
                    </button>
                  </span>
                </li>
              </ul>
              <FormControl
                v-model="placeQuery"
                type="text"
                :label="__('Add a place')"
                :placeholder="__('Search a state, city or country')"
                autocomplete="off"
                @input="findPlaces"
              />
              <PickList
                :items="placeResults"
                :loading="searching === 'place'"
                :label="(p: Place) => `${p.name}${p.detail ? ' · ' + p.detail : ''}`"
                :id="(p: Place) => p.key"
                :query="placeQuery"
                @pick="addPlace"
              />
            </div>

            <div class="grid grid-cols-2 gap-3">
              <FormControl
                v-model="form.audience.age_min"
                type="number"
                :label="__('Youngest')"
                :min="18"
                :max="65"
              />
              <FormControl
                v-model="form.audience.age_max"
                type="number"
                :label="__('Oldest')"
                :min="18"
                :max="65"
              />
            </div>

            <div class="flex flex-col gap-2">
              <span class="text-xs text-ink-gray-5">{{
                __("Interests (optional)")
              }}</span>
              <ul
                v-if="form.audience.interests.length"
                class="flex flex-wrap gap-2"
                role="list"
              >
                <li v-for="(item, i) in form.audience.interests" :key="item.id">
                  <span
                    class="inline-flex min-h-8 items-center gap-1 rounded-md bg-surface-gray-2 ps-2 text-sm text-ink-gray-8"
                  >
                    {{ item.name }}
                    <button
                      type="button"
                      class="flex size-8 items-center justify-center rounded-md text-ink-gray-6 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                      :aria-label="__('Remove {0}', item.name)"
                      @click="form.audience.interests.splice(i, 1)"
                    >
                      <LucideX class="size-3.5" aria-hidden="true" />
                    </button>
                  </span>
                </li>
              </ul>
              <FormControl
                v-model="interestQuery"
                type="text"
                :label="__('Add an interest')"
                :placeholder="__('For example: cooking, fitness, weddings')"
                autocomplete="off"
                @input="findInterests"
              />
              <PickList
                :items="interestResults"
                :loading="searching === 'interest'"
                :label="(i: Interest) => i.name"
                :id="(i: Interest) => i.id"
                :query="interestQuery"
                @pick="addInterest"
              />
            </div>

            <label
              class="flex min-h-11 items-start gap-2 text-base text-ink-gray-8"
            >
              <input
                v-model="form.audience.advantage_audience"
                type="checkbox"
                class="mt-1 size-4 accent-brand"
              />
              <span>
                {{
                  __(
                    "Let Meta find more people like them (Advantage+ audience)"
                  )
                }}
                <span class="block text-p-sm text-ink-gray-6">
                  {{
                    __(
                      "Recommended. Meta treats the ages and interests above as hints and may reach a few more people."
                    )
                  }}
                </span>
              </span>
            </label>
          </div>
        </details>

        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "Where it shows: automatic, on Facebook, Instagram and Messenger. Meta picks the best places."
            )
          }}
        </p>

        <section
          class="flex flex-col gap-1 rounded-lg bg-surface-gray-1 px-3 py-3"
          :aria-label="__('Summary')"
          aria-live="polite"
        >
          <p class="text-base-medium text-ink-gray-9">
            <template v-if="preview.data">{{ preview.data.summary }}</template>
            <template v-else-if="preview.loading">{{
              __("Working out the summary…")
            }}</template>
            <template v-else>{{
              __("Fill in the budget and dates to see the summary.")
            }}</template>
          </p>
          <p v-if="preview.data" class="text-p-sm text-ink-gray-6">
            {{
              __(
                "It never spends more than this. {0} is left of this month's limit.",
                formatMoney(preview.data.left, currency)
              )
            }}
          </p>
          <p
            v-if="preview.data?.over_cap"
            role="alert"
            class="flex items-start gap-2 text-p-sm text-danger"
          >
            <LucideCircleAlert
              class="mt-0.5 size-4 shrink-0"
              aria-hidden="true"
            />
            {{
              __(
                "This is more than the month's limit. Lower the budget, or ask the Digital Marketing Head to raise the limit."
              )
            }}
          </p>
          <p v-if="preview.error" role="alert" class="text-p-sm text-danger">
            {{ errorText(preview.error, __("Couldn't check this boost.")) }}
          </p>
        </section>

        <p
          v-if="!canSpend"
          class="flex items-start gap-2 text-p-sm text-ink-gray-7"
          role="note"
        >
          <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {{
            __(
              "The Digital Marketing Head approves a boost before it goes live. You'll be told when they do."
            )
          }}
        </p>
        <ErrorMessage :message="error" />
      </form>
    </template>
    <template #actions>
      <div class="flex flex-wrap justify-end gap-2">
        <Button :label="__('Cancel')" @click="open = false" />
        <Button
          type="submit"
          form="boost-form"
          variant="solid"
          :label="canSpend ? __('Start boost') : __('Ask for approval')"
          :loading="saving"
          :disabled="!form || !preview.data || preview.data.over_cap"
        >
          <template #prefix>
            <component
              :is="canSpend ? LucideRocket : LucideSend"
              class="size-4"
              aria-hidden="true"
            />
          </template>
        </Button>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useDebounceFn } from "@vueuse/core";
import {
  Button,
  call,
  createResource,
  Dialog,
  ErrorMessage,
  FormControl,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideInfo from "~icons/lucide/info";
import LucideRocket from "~icons/lucide/rocket";
import LucideSend from "~icons/lucide/send";
import LucideUsers from "~icons/lucide/users";
import LucideX from "~icons/lucide/x";
import { formatMoney, GOAL_HINTS } from "../boost";
import PickList from "./PickList.vue";

interface Place {
  type: string;
  key: string;
  name: string;
  detail?: string;
}
interface Interest {
  id: string;
  name: string;
}
interface Audience {
  locations: Place[];
  age_min: number;
  age_max: number;
  interests: Interest[];
  advantage_audience: boolean;
}
interface BoostForm {
  target: string;
  goal: string;
  budget_type: string;
  budget_amount: number;
  start_date: string;
  end_date: string;
  audience: Audience;
}

const props = defineProps<{
  post: string;
  targets: string[];
  goals: string[];
  currency: string;
  canSpend: boolean;
  initial?: Partial<BoostForm> | null;
}>();
const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ (e: "done"): void }>();

const form = ref<BoostForm | null>(null);
const error = ref("");
const saving = ref(false);
const audienceOpen = ref(false);
const placeQuery = ref("");
const interestQuery = ref("");
const placeResults = ref<Place[]>([]);
const interestResults = ref<Interest[]>([]);
const searching = ref<"place" | "interest" | null>(null);

const where = computed(
  () => form.value?.audience.locations.map((p) => p.name).join(", ") ?? ""
);

const defaults = createResource({
  url: "helpdesk.api.meta_ads.get_defaults",
  makeParams: () => ({ post: props.post }),
  onSuccess(d: BoostForm) {
    form.value = { ...d, target: props.targets[0], ...props.initial };
  },
});

watch(open, (isOpen) => {
  if (!isOpen) return;
  form.value = null;
  error.value = "";
  placeQuery.value = interestQuery.value = "";
  placeResults.value = interestResults.value = [];
  defaults.reload();
});

const preview = createResource({
  url: "helpdesk.api.meta_ads.preview",
  makeParams: () => ({ post: props.post, values: form.value }),
});
const refreshPreview = useDebounceFn(() => {
  const f = form.value;
  if (!f || !f.budget_amount || !f.start_date || !f.end_date) return;
  preview.reload();
}, 500);
watch(form, refreshPreview, { deep: true });

const findPlaces = useDebounceFn(async () => {
  if (placeQuery.value.trim().length < 2) {
    placeResults.value = [];
    return;
  }
  searching.value = "place";
  try {
    placeResults.value = await call("helpdesk.api.meta_ads.search_locations", {
      post: props.post,
      q: placeQuery.value.trim(),
    });
  } catch (e) {
    error.value = errorText(e, __("Couldn't search places."));
  } finally {
    searching.value = null;
  }
}, 350);

const findInterests = useDebounceFn(async () => {
  if (interestQuery.value.trim().length < 2) {
    interestResults.value = [];
    return;
  }
  searching.value = "interest";
  try {
    interestResults.value = await call(
      "helpdesk.api.meta_ads.search_interests",
      {
        post: props.post,
        q: interestQuery.value.trim(),
      }
    );
  } catch (e) {
    error.value = errorText(e, __("Couldn't search interests."));
  } finally {
    searching.value = null;
  }
}, 350);

function addPlace(place: Place) {
  const list = form.value!.audience.locations;
  if (!list.some((p) => p.key === place.key)) list.push(place);
  placeQuery.value = "";
  placeResults.value = [];
}
function addInterest(item: Interest) {
  const list = form.value!.audience.interests;
  if (!list.some((i) => i.id === item.id)) list.push(item);
  interestQuery.value = "";
  interestResults.value = [];
}

async function submit() {
  error.value = "";
  saving.value = true;
  try {
    const boost = await call("helpdesk.api.meta_ads.submit", {
      post: props.post,
      values: form.value,
    });
    if (boost.status === "Failed") {
      error.value = boost.failure_reason || __("The boost didn't start.");
      emit("done");
      return;
    }
    toast.success(
      boost.status === "Active"
        ? __("Boost started. Meta may take a little while to review the ad.")
        : __("Sent to the Digital Marketing Head for approval.")
    );
    open.value = false;
    emit("done");
  } catch (e) {
    error.value = errorText(e, __("Couldn't start the boost. Try again."));
  } finally {
    saving.value = false;
  }
}
</script>
