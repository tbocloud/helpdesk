<template>
  <section
    class="mt-4 flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
    :aria-label="__('Ads')"
  >
    <h3 class="text-base-medium text-ink-gray-9">{{ __("Paid ads") }}</h3>

    <template v-if="!conn.ads_allowed">
      <p class="flex items-start gap-2 text-p-sm text-ink-gray-7">
        <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        {{
          __(
            "Reconnect Meta to allow ads. The client's Facebook admin is asked to allow ads as well as posting; nothing else changes."
          )
        }}
      </p>
      <div class="flex justify-end">
        <Button
          variant="solid"
          :label="__('Reconnect Meta to allow ads')"
          @click="emit('reconnect')"
        />
      </div>
    </template>

    <template v-else-if="picking || !conn.ad_account_id">
      <p class="text-p-sm text-ink-gray-7">
        {{
          __(
            "Pick the client's ad account. The client must have added TBO's business as a partner on it, or you must have an advertiser role on it."
          )
        }}
      </p>
      <div
        v-if="accounts.loading"
        class="h-16 animate-pulse rounded-lg bg-surface-gray-1"
        aria-busy="true"
      />
      <p v-else-if="accounts.error" role="alert" class="text-p-sm text-danger">
        {{ errorText(accounts.error, __("Couldn't load the ad accounts.")) }}
        <Button
          variant="ghost"
          :label="__('Try again')"
          @click="accounts.reload()"
        />
      </p>
      <p v-else-if="!accounts.data?.length" class="text-p-sm text-ink-gray-7">
        {{
          __(
            "No ad account found. Ask the client to add TBO's business as a partner on their ad account, then connect Meta again."
          )
        }}
      </p>
      <fieldset v-else class="flex flex-col gap-2">
        <legend class="sr-only">{{ __("Ad accounts") }}</legend>
        <label
          v-for="a in accounts.data"
          :key="a.id"
          class="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-outline-gray-2 px-3 py-2 has-[:checked]:border-brand has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-highlight"
          :class="!a.usable && 'opacity-60'"
        >
          <input
            v-model="chosen"
            type="radio"
            name="ad-account"
            :value="a.id"
            :disabled="!a.usable"
            class="accent-brand"
          />
          <span class="min-w-0 flex-1">
            <span class="block truncate text-base text-ink-gray-9">{{
              a.name
            }}</span>
            <span class="block text-p-sm text-ink-gray-6">
              {{ a.currency
              }}<template v-if="a.business"> · {{ a.business }}</template>
            </span>
          </span>
          <TaskyBadge
            :tone="a.usable ? 'success' : 'danger'"
            :icon="a.usable ? LucideCircleCheck : LucideCircleAlert"
            :label="a.status"
          />
        </label>
      </fieldset>
      <div class="flex flex-wrap justify-end gap-2">
        <Button v-if="picking" :label="__('Cancel')" @click="picking = false" />
        <Button
          variant="solid"
          :label="__('Use this ad account')"
          :disabled="!chosen"
          :loading="saving"
          @click="select"
        />
      </div>
    </template>

    <template v-else>
      <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-p-sm">
        <dt class="text-ink-gray-6">{{ __("Ad account") }}</dt>
        <dd class="flex flex-wrap items-center gap-2 text-ink-gray-8">
          {{ conn.ad_account_name }}
          <TaskyBadge
            :tone="conn.ad_account_status === 'Active' ? 'success' : 'danger'"
            :icon="
              conn.ad_account_status === 'Active'
                ? LucideCircleCheck
                : LucideCircleAlert
            "
            :label="__(conn.ad_account_status || 'Not available')"
          />
        </dd>
        <dt class="text-ink-gray-6">{{ __("Currency") }}</dt>
        <dd class="text-ink-gray-8">{{ conn.ad_account_currency }}</dd>
        <dt class="text-ink-gray-6">{{ __("Monthly limit") }}</dt>
        <dd class="text-ink-gray-8">
          <form
            v-if="canChangeCap"
            class="flex flex-wrap items-end gap-2"
            @submit.prevent="saveCap"
          >
            <FormControl
              v-model="cap"
              type="number"
              :min="0"
              :label="__('Most to plan per month')"
            />
            <Button
              type="submit"
              :label="__('Save limit')"
              :loading="saving"
              :disabled="Number(cap) === conn.monthly_ad_cap"
            />
          </form>
          <template v-else>
            {{
              formatMoney(conn.monthly_ad_cap ?? 0, conn.ad_account_currency)
            }}
            <span class="text-ink-gray-6"
              >· {{ __("The Digital Marketing Head can change it.") }}</span
            >
          </template>
        </dd>
      </dl>
      <p
        v-if="conn.ad_account_status !== 'Active'"
        role="alert"
        class="text-p-sm text-danger"
      >
        {{
          __(
            "This ad account can't run ads right now. The client fixes it in Meta Business Settings (often a payment problem)."
          )
        }}
      </p>
      <p v-else class="text-p-sm text-ink-gray-6">
        {{
          __(
            "The client needs a payment method on this ad account; Meta charges them directly."
          )
        }}
      </p>
      <div class="flex justify-end">
        <Button :label="__('Change ad account')" @click="startPicking" />
      </div>
    </template>
    <ErrorMessage :message="error" />
  </section>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  call,
  createResource,
  ErrorMessage,
  FormControl,
  toast,
} from "frappe-ui";
import { ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideInfo from "~icons/lucide/info";
import { formatMoney } from "../../content/boost";

interface AdsConnection {
  ads_allowed: boolean;
  ad_account_id?: string | null;
  ad_account_name?: string | null;
  ad_account_currency?: string | null;
  ad_account_status?: string | null;
  monthly_ad_cap?: number;
}

const props = defineProps<{
  projectId: string;
  conn: AdsConnection;
  canChangeCap: boolean;
}>();
const emit = defineEmits<{ (e: "changed"): void; (e: "reconnect"): void }>();

const picking = ref(false);
const chosen = ref("");
const saving = ref(false);
const error = ref("");
const cap = ref<number | string>(props.conn.monthly_ad_cap ?? 0);
watch(
  () => props.conn.monthly_ad_cap,
  (v) => (cap.value = v ?? 0)
);

const accounts = createResource({
  url: "helpdesk.api.meta_ads.list_ad_accounts",
  makeParams: () => ({ project: props.projectId }),
});
watch(
  () => [props.conn.ads_allowed, props.conn.ad_account_id, picking.value],
  () => {
    if (props.conn.ads_allowed && (picking.value || !props.conn.ad_account_id))
      accounts.reload();
  },
  { immediate: true }
);

function startPicking() {
  chosen.value = props.conn.ad_account_id ?? "";
  picking.value = true;
}

async function select() {
  error.value = "";
  saving.value = true;
  try {
    await call("helpdesk.api.meta_ads.select_ad_account", {
      project: props.projectId,
      account_id: chosen.value,
    });
    picking.value = false;
    toast.success(__("Ad account saved"));
    emit("changed");
  } catch (e) {
    error.value = errorText(e, __("Couldn't use that ad account."));
  } finally {
    saving.value = false;
  }
}

async function saveCap() {
  error.value = "";
  saving.value = true;
  try {
    await call("helpdesk.api.meta_ads.set_monthly_cap", {
      project: props.projectId,
      amount: Number(cap.value),
    });
    toast.success(__("Monthly limit saved"));
    emit("changed");
  } catch (e) {
    error.value = errorText(e, __("Couldn't save the limit."));
  } finally {
    saving.value = false;
  }
}
</script>
