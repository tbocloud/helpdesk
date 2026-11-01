<template>
  <section
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-label="__('Place')"
  >
    <div
      class="flex items-center gap-2 border-b border-outline-gray-1 px-4 py-3"
    >
      <h2 class="text-base-medium text-ink-gray-9">{{ __("Place") }}</h2>
      <Button
        v-if="canWrite && filled"
        class="ml-auto"
        variant="ghost"
        :label="__('Edit place')"
        @click="openEdit"
      >
        <template #prefix>
          <LucidePencil class="size-4" aria-hidden="true" />
        </template>
        <span class="hidden sm:inline">{{ __("Edit") }}</span>
      </Button>
    </div>

    <div v-if="!filled" class="flex flex-col items-start gap-3 px-4 py-4">
      <p class="text-p-sm text-ink-gray-6">
        {{
          canWrite
            ? __(
                "No place saved yet. Add the client's Google profile and a map pin, so whoever goes to meet them can go straight there."
              )
            : __("No place has been saved for this lead.")
        }}
      </p>
      <Button v-if="canWrite" :label="__('Add place')" @click="openEdit">
        <template #prefix>
          <LucideMapPin class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>

    <div v-else class="flex flex-col gap-3 px-4 py-4">
      <p
        v-if="place.location_note"
        class="whitespace-pre-line break-words text-base text-ink-gray-8"
      >
        {{ place.location_note }}
      </p>
      <div class="flex flex-wrap gap-2">
        <Button
          v-if="directions"
          :link="directions"
          :label="__('Get directions')"
        >
          <template #prefix>
            <LucideNavigation class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-else-if="place.maps_url"
          :link="place.maps_url"
          :label="__('Open in Maps')"
        >
          <template #prefix>
            <LucideMap class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-if="place.google_profile_url"
          :link="place.google_profile_url"
          :label="__('Google profile')"
        >
          <template #prefix>
            <LucideExternalLink class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-if="embed"
          :label="showMap ? __('Hide map') : __('Show map')"
          :aria-expanded="showMap"
          @click="showMap = !showMap"
        >
          <template #prefix>
            <LucideMap class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
      <p
        v-if="hasPin(place)"
        class="font-mono text-xs tabular-nums text-ink-gray-5"
      >
        {{ place.latitude }}, {{ place.longitude }}
      </p>
      <iframe
        v-if="embed && showMap"
        :src="embed"
        :title="__('Map of the lead\'s place')"
        class="aspect-video w-full rounded-lg border border-outline-gray-2 bg-surface-gray-1"
        loading="lazy"
        referrerpolicy="no-referrer"
        allowfullscreen
      />
    </div>

    <Dialog v-model:open="showEdit" :title="__('Place')" size="md">
      <form
        :id="formId"
        class="flex flex-col gap-4"
        novalidate
        @submit.prevent="submit"
      >
        <FormControl
          v-model="form.google_profile_url"
          type="url"
          :label="__('Google profile link')"
          :placeholder="__('Paste the client\'s Google Business Profile link')"
          :description="
            __('From Google Maps: open the business, then Share, then copy.')
          "
          maxlength="500"
        />
        <FormControl
          v-model="form.maps_url"
          type="url"
          :label="__('Map link')"
          :placeholder="__('Paste a Google Maps place or pin link')"
          maxlength="500"
          @blur="takePinFromLink"
        />
        <fieldset class="flex flex-col gap-2">
          <legend class="mb-1 text-xs text-ink-gray-5">
            {{ __("Map pin") }}
          </legend>
          <div class="grid grid-cols-2 gap-3">
            <FormControl
              v-model="form.latitude"
              type="text"
              inputmode="decimal"
              :label="__('Latitude')"
              class="font-mono"
            />
            <FormControl
              v-model="form.longitude"
              type="text"
              inputmode="decimal"
              :label="__('Longitude')"
              class="font-mono"
            />
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              :label="__('Use my current location')"
              :loading="locating"
              @click="useMyLocation"
            >
              <template #prefix>
                <LucideLocateFixed class="size-4" aria-hidden="true" />
              </template>
            </Button>
            <span class="text-p-xs text-ink-gray-5">{{
              __("Stand at the client's door for an exact pin.")
            }}</span>
          </div>
          <p v-if="pinHint" role="status" class="text-p-sm text-ink-gray-6">
            {{ pinHint }}
          </p>
          <p v-if="locationError" role="alert" class="text-p-sm text-danger">
            {{ locationError }}
          </p>
        </fieldset>
        <FormControl
          v-model="form.location_note"
          type="textarea"
          :rows="3"
          :label="__('How to find it')"
          :placeholder="__('2nd floor, above SBI, parking behind')"
          maxlength="500"
        />
        <p v-if="error" role="alert" class="text-p-sm text-danger">
          {{ error }}
        </p>
      </form>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button
            type="button"
            :label="__('Cancel')"
            @click="showEdit = false"
          />
          <Button
            variant="solid"
            type="submit"
            :form="formId"
            :label="__('Save')"
            :loading="save.loading"
          />
        </div>
      </template>
    </Dialog>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, Dialog, FormControl, toast } from "frappe-ui";
import { computed, reactive, ref, useId } from "vue";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideLocateFixed from "~icons/lucide/locate-fixed";
import LucideMap from "~icons/lucide/map";
import LucideMapPin from "~icons/lucide/map-pin";
import LucideNavigation from "~icons/lucide/navigation";
import LucidePencil from "~icons/lucide/pencil";
import {
  coordsFromMapsUrl,
  currentPosition,
  directionsUrl,
  embedUrl,
  geolocationMessage,
  hasPin,
  hasPlace,
  type LeadPlace,
} from "./place";

const props = defineProps<{
  leadId: string;
  place: LeadPlace;
  canWrite: boolean;
}>();
const emit = defineEmits<{ (e: "saved"): void }>();

const formId = `lead-place-${useId()}`;
const showEdit = ref(false);
const showMap = ref(false);
const error = ref("");
const locationError = ref("");
const pinHint = ref("");
const locating = ref(false);
const form = reactive({
  google_profile_url: "",
  maps_url: "",
  latitude: "",
  longitude: "",
  location_note: "",
});

const filled = computed(() => hasPlace(props.place));
const directions = computed(() => directionsUrl(props.place));
const embed = computed(() => embedUrl(props.place));

function openEdit() {
  const p = props.place;
  form.google_profile_url = p.google_profile_url || "";
  form.maps_url = p.maps_url || "";
  form.latitude = p.latitude == null ? "" : String(p.latitude);
  form.longitude = p.longitude == null ? "" : String(p.longitude);
  form.location_note = p.location_note || "";
  error.value = locationError.value = pinHint.value = "";
  showEdit.value = true;
}

/** A long map link already says where the place is, so the pin needn't be typed. */
function takePinFromLink() {
  if (form.latitude.trim() || form.longitude.trim()) return;
  const found = coordsFromMapsUrl(form.maps_url);
  if (!found) return;
  form.latitude = String(found.latitude);
  form.longitude = String(found.longitude);
  pinHint.value = __("Pin taken from the map link.");
}

async function useMyLocation() {
  locating.value = true;
  locationError.value = pinHint.value = "";
  try {
    const position = await currentPosition();
    form.latitude = String(position.latitude);
    form.longitude = String(position.longitude);
    pinHint.value = __("Pin set to where you are now.");
  } catch (e) {
    locationError.value = geolocationMessage(e);
  } finally {
    locating.value = false;
  }
}

const save = createResource({
  url: "helpdesk.api.leads.update_lead",
  method: "POST",
  onSuccess() {
    toast.success(__("Place saved"));
    showEdit.value = false;
    emit("saved");
  },
  onError(e: unknown) {
    error.value = errorText(
      e,
      __("Couldn't save the place. Check your connection and try again.")
    );
  },
});

function submit() {
  if (save.loading) return;
  error.value = "";
  const latitude = form.latitude.trim();
  const longitude = form.longitude.trim();
  if (!latitude !== !longitude) {
    error.value = __("Give both latitude and longitude, or neither.");
    return;
  }
  const lat = latitude ? Number(latitude) : null;
  const lng = longitude ? Number(longitude) : null;
  if (
    (lat !== null && !(Math.abs(lat) <= 90)) ||
    (lng !== null && !(Math.abs(lng) <= 180))
  ) {
    error.value = __(
      "Latitude is between -90 and 90 and longitude between -180 and 180."
    );
    return;
  }
  save.submit({
    name: props.leadId,
    data: {
      google_profile_url: form.google_profile_url.trim(),
      maps_url: form.maps_url.trim(),
      latitude: lat,
      longitude: lng,
      location_note: form.location_note.trim(),
    },
  });
}
</script>
