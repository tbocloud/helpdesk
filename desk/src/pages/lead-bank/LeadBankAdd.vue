<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <nav
          class="flex min-w-0 items-center gap-1.5 text-lg-medium"
          :aria-label="__('Breadcrumb')"
        >
          <router-link
            :to="{ name: 'LeadBank' }"
            class="shrink-0 rounded text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            >{{ __("Lead Bank") }}</router-link
          >
          <LucideChevronRight
            class="size-4 shrink-0 text-ink-gray-4"
            aria-hidden="true"
          />
          <span class="truncate text-ink-gray-9">{{ __("Add a lead") }}</span>
        </nav>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-y-auto overflow-x-hidden">
      <div class="mx-auto flex w-full max-w-xl flex-col gap-5 px-4 py-5">
        <!-- done: what happened, then the next lead -->
        <section
          v-if="result"
          class="flex flex-col items-center gap-4 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-8 text-center"
          role="status"
        >
          <LucideCircleCheck
            v-if="result.created"
            class="size-8 text-success"
            aria-hidden="true"
          />
          <LucideInfo v-else class="size-8 text-info" aria-hidden="true" />
          <p class="text-lg-medium text-ink-gray-9">{{ result.message }}</p>
          <p v-if="result.created" class="text-p-sm text-ink-gray-6">
            {{ __("Our team will call them. You can follow it in My leads.") }}
          </p>
          <div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
            <Button
              variant="solid"
              size="lg"
              :label="__('Add another lead')"
              @click="reset"
            >
              <template #prefix>
                <LucideCamera class="size-5" aria-hidden="true" />
              </template>
            </Button>
            <Button
              size="lg"
              :label="__('See my leads')"
              @click="router.push({ name: 'LeadBank' })"
            />
          </div>
        </section>

        <template v-else>
          <header class="flex flex-col gap-1">
            <h1 class="text-xl-semibold text-ink-gray-9">
              {{ __("Add a lead") }}
            </h1>
            <p class="text-p-sm text-ink-gray-6">
              {{
                __(
                  "Take a photo of a shop board, visiting card, banner or ad. We read it and fill in the details for you."
                )
              }}
            </p>
          </header>

          <!-- the photos: one big button, the gallery second -->
          <section class="flex flex-col gap-3" :aria-label="__('Photos')">
            <Button
              variant="solid"
              size="xl"
              class="w-full !h-14 text-lg"
              :label="
                photos.length ? __('Take another photo') : __('Take a photo')
              "
              :disabled="full || preparing"
              :loading="preparing"
              @click="camera?.click()"
            >
              <template #prefix>
                <LucideCamera class="size-6" aria-hidden="true" />
              </template>
            </Button>
            <Button
              class="w-full"
              :label="__('Choose from gallery')"
              :disabled="full || preparing"
              @click="gallery?.click()"
            >
              <template #prefix>
                <LucideImagePlus class="size-4" aria-hidden="true" />
              </template>
            </Button>
            <!-- two pickers: `capture` opens the camera only, so the gallery needs its own -->
            <input
              ref="camera"
              type="file"
              accept="image/*"
              capture="environment"
              class="hidden"
              tabindex="-1"
              aria-hidden="true"
              @change="onPick"
            />
            <input
              ref="gallery"
              type="file"
              accept="image/*"
              multiple
              class="hidden"
              tabindex="-1"
              aria-hidden="true"
              @change="onPick"
            />
            <ul
              v-if="photos.length"
              role="list"
              class="grid grid-cols-3 gap-2 sm:grid-cols-5"
            >
              <li
                v-for="(photo, index) in photos"
                :key="photo.id"
                class="relative aspect-square overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-gray-2"
              >
                <img
                  :src="photo.preview"
                  :alt="__('Photo {0}', String(index + 1))"
                  class="size-full object-cover"
                />
                <button
                  type="button"
                  class="absolute right-1 top-1 flex size-8 items-center justify-center rounded-full bg-surface-base text-ink-gray-8 shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                  :aria-label="__('Remove photo {0}', String(index + 1))"
                  @click="removePhoto(photo.id)"
                >
                  <LucideX class="size-4" aria-hidden="true" />
                </button>
              </li>
            </ul>
            <p
              v-if="photoError"
              role="alert"
              class="flex items-start gap-2 text-p-sm text-danger"
            >
              <LucideCircleAlert
                class="mt-0.5 size-4 shrink-0"
                aria-hidden="true"
              />
              {{ photoError }}
            </p>
          </section>

          <p
            v-if="scanning"
            role="status"
            class="flex items-center gap-2 text-p-sm text-ink-gray-7"
          >
            <LucideLoaderCircle
              class="size-4 animate-spin"
              aria-hidden="true"
            />
            {{ __("Reading the photo…") }}
          </p>
          <p
            v-else-if="scanMessage"
            role="status"
            class="flex items-start gap-2 text-p-sm text-ink-gray-7"
          >
            <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {{ scanMessage }}
          </p>

          <p
            v-if="duplicate"
            role="alert"
            class="flex items-start gap-2 rounded-lg bg-info-soft px-3 py-2 text-p-sm text-info"
          >
            <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span>
              {{ duplicate.message }}
              {{
                __(
                  "You can still send it: we add your note to the lead, and whoever found it first keeps the credit."
                )
              }}
            </span>
          </p>

          <!-- the form shows once there is a photo to fill it from -->
          <form
            v-if="photos.length"
            :id="formId"
            class="flex flex-col gap-4"
            novalidate
            @submit.prevent="submit"
          >
            <FormControl
              v-model="form.company_name"
              :label="__('Business name')"
              maxlength="140"
              autocomplete="off"
            />
            <FormControl
              v-model="form.contact_name"
              :label="__('Contact person')"
              maxlength="140"
              autocomplete="off"
            />
            <FormControl
              v-model="form.mobile_no"
              type="tel"
              inputmode="tel"
              :label="__('Phone')"
              maxlength="40"
              autocomplete="off"
              @blur="detectRegion"
            />
            <FormControl
              v-if="form.phone || morePhone"
              v-model="form.phone"
              type="tel"
              inputmode="tel"
              :label="__('Second phone')"
              maxlength="40"
              autocomplete="off"
            />
            <button
              v-else
              type="button"
              class="-mt-2 self-start rounded text-p-sm text-brand-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              @click="morePhone = true"
            >
              {{ __("Add a second phone") }}
            </button>
            <FormControl
              v-model="form.email_id"
              type="email"
              inputmode="email"
              :label="__('Email')"
              maxlength="140"
              autocomplete="off"
            />
            <FormControl
              v-model="form.business_type"
              :label="__('What do they do?')"
              maxlength="80"
              autocomplete="off"
            />
            <FormControl
              v-model="form.address"
              type="textarea"
              :rows="2"
              :label="__('Address')"
              maxlength="300"
            />

            <fieldset class="flex flex-col gap-2">
              <legend class="text-p-sm text-ink-gray-7">
                {{ __("Country") }}
              </legend>
              <TabButtons
                :model-value="region"
                :options="regionOptions"
                @update:model-value="chooseRegion"
              />
              <p class="text-p-xs text-ink-gray-6">
                {{ regionHint }}
              </p>
            </fieldset>

            <FormControl
              v-model="form.note"
              type="textarea"
              :rows="2"
              :label="__('Anything else we should know? (optional)')"
              maxlength="2000"
            />

            <p class="flex items-center gap-2 text-p-sm text-ink-gray-7">
              <LucideMapPin class="size-4 shrink-0" aria-hidden="true" />
              <template v-if="place">
                {{ __("Your location is added, so we can find the place.") }}
                <button
                  type="button"
                  class="rounded text-brand-ink underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                  @click="place = null"
                >
                  {{ __("Remove") }}
                </button>
              </template>
              <template v-else>
                {{ placeNote }}
                <button
                  type="button"
                  class="rounded text-brand-ink underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                  @click="findPlace"
                >
                  {{ __("Use my location") }}
                </button>
              </template>
            </p>

            <p
              v-if="errorMessage"
              role="alert"
              class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
            >
              <LucideCircleAlert
                class="mt-0.5 size-4 shrink-0"
                aria-hidden="true"
              />
              <span>{{ errorMessage }}</span>
            </p>
          </form>
        </template>
      </div>
    </div>

    <!-- the one primary action, always in reach on a phone -->
    <div
      v-if="photos.length && !result"
      class="border-t border-outline-gray-2 bg-surface-base px-4 py-3"
    >
      <div class="mx-auto max-w-xl">
        <Button
          variant="solid"
          size="lg"
          class="w-full"
          type="submit"
          :form="formId"
          :label="__('Submit lead')"
          :loading="submitting"
          :disabled="scanning || preparing"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import {
  currentPosition,
  geolocationMessage,
  preparePhoto,
} from "@/pages/leads/place";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, FormControl, TabButtons } from "frappe-ui";
import { computed, onMounted, reactive, ref, useId } from "vue";
import { useRouter } from "vue-router";
import LucideCamera from "~icons/lucide/camera";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideImagePlus from "~icons/lucide/image-plus";
import LucideInfo from "~icons/lucide/info";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucideMapPin from "~icons/lucide/map-pin";
import LucideX from "~icons/lucide/x";
import {
  blankForm,
  earnText,
  REGION_LABEL,
  REGIONS,
  type Duplicate,
  type LeadBankOptions,
  type Region,
  type ScanResult,
  type SubmitResult,
} from "./leadBank";

interface Photo {
  id: number;
  filename: string;
  content: string;
  preview: string;
}

const router = useRouter();
const formId = `lead-bank-${useId()}`;
const camera = ref<HTMLInputElement | null>(null);
const gallery = ref<HTMLInputElement | null>(null);

const options = ref<LeadBankOptions>();
const photos = ref<Photo[]>([]);
const form = reactive(blankForm());
const region = ref<Region | "">("");
// the person picked the region: a phone or a position never changes it afterwards
let regionChosen = false;
const place = ref<{ latitude: number; longitude: number } | null>(null);
const placeNote = ref(__("Add your location so we can find the place."));
const morePhone = ref(false);
const duplicate = ref<Duplicate | null>(null);
const scanMessage = ref("");
const photoError = ref("");
const errorMessage = ref("");
const preparing = ref(false);
const scanning = ref(false);
const submitting = ref(false);
const result = ref<SubmitResult | null>(null);
let nextId = 1;

const maxPhotos = computed(() => options.value?.max_photos ?? 5);
const full = computed(() => photos.value.length >= maxPhotos.value);
const regionOptions = computed(() =>
  REGIONS.map((r) => ({ label: REGION_LABEL[r], value: r }))
);
const regionHint = computed(() => earnText(options.value));

onMounted(() => {
  // the rates and the photo limit; a failure leaves the form working with its defaults
  call("helpdesk.api.lead_bank.get_options")
    .then((data: LeadBankOptions) => (options.value = data))
    .catch(() => undefined);
});

/** Choosing a country by hand wins over anything detected afterwards. */
function chooseRegion(value: unknown) {
  region.value = value as Region;
  regionChosen = true;
}

async function onPick(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []).slice(
    0,
    maxPhotos.value - photos.value.length
  );
  input.value = "";
  if (!files.length) return;
  photoError.value = "";
  preparing.value = true;
  try {
    for (const file of files) {
      const prepared = await preparePhoto(file);
      photos.value.push({
        id: nextId++,
        ...prepared,
        preview: `data:image/jpeg;base64,${prepared.content}`,
      });
    }
  } catch (e) {
    photoError.value = (e as Error).message;
  } finally {
    preparing.value = false;
  }
  if (!place.value) findPlace(true);
  scan();
}

function removePhoto(id: number) {
  photos.value = photos.value.filter((photo) => photo.id !== id);
  if (!photos.value.length) {
    scanMessage.value = "";
    duplicate.value = null;
  }
}

/** Fills what is still empty from the photos, so nothing the person typed is overwritten. */
async function scan() {
  if (!photos.value.length || scanning.value) return;
  scanning.value = true;
  scanMessage.value = "";
  try {
    const found: ScanResult = await call("helpdesk.api.lead_bank.scan_photos", {
      photos: photos.value.map(({ filename, content }) => ({
        filename,
        content,
      })),
      latitude: place.value?.latitude,
      longitude: place.value?.longitude,
    });
    for (const [key, value] of Object.entries(found.fields)) {
      const field = key as keyof typeof form;
      if (value && !form[field]) form[field] = value;
    }
    if (found.fields.phone) morePhone.value = true;
    if (found.region && !regionChosen) region.value = found.region;
    duplicate.value = found.duplicate;
    scanMessage.value = found.message ?? "";
  } catch (e) {
    scanMessage.value = errorText(
      e,
      __("We couldn't read the photo this time. Please fill in the details.")
    );
  } finally {
    scanning.value = false;
  }
}

async function findPlace(quiet = false) {
  try {
    place.value = await currentPosition();
  } catch (e) {
    if (quiet !== true) placeNote.value = geolocationMessage(e);
  }
}

/** The phone's country code names the region, unless the person already chose one. */
async function detectRegion() {
  if (regionChosen || !form.mobile_no.trim()) return;
  try {
    const found = await call("helpdesk.api.lead_bank.detect_region", {
      phones: [form.mobile_no, form.phone].filter(Boolean),
      latitude: place.value?.latitude,
      longitude: place.value?.longitude,
    });
    if (found?.region && !regionChosen) region.value = found.region;
  } catch {
    // the person can still pick it
  }
}

function problem(): string {
  if (!(form.company_name.trim() || form.contact_name.trim()))
    return __("Add the business name or the contact person.");
  if (!(form.mobile_no.trim() || form.phone.trim() || form.email_id.trim()))
    return __("Add a phone number or an email, so our team can reach them.");
  if (!region.value) return __("Pick the country: India, UAE or KSA.");
  return "";
}

async function submit() {
  if (submitting.value) return;
  errorMessage.value = problem();
  if (errorMessage.value) return;
  submitting.value = true;
  try {
    result.value = await call("helpdesk.api.lead_bank.submit_lead", {
      data: {
        ...form,
        region: region.value,
        latitude: place.value?.latitude,
        longitude: place.value?.longitude,
      },
      photos: photos.value.map(({ filename, content }) => ({
        filename,
        content,
      })),
    });
  } catch (e) {
    errorMessage.value = errorText(
      e,
      __("Couldn't send the lead. Check your connection and try again.")
    );
  } finally {
    submitting.value = false;
  }
}

function reset() {
  Object.assign(form, blankForm());
  photos.value = [];
  region.value = "";
  regionChosen = false;
  place.value = null;
  morePhone.value = false;
  duplicate.value = null;
  scanMessage.value = "";
  errorMessage.value = "";
  result.value = null;
}
</script>
