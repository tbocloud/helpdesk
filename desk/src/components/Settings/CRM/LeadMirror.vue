<template>
  <SettingsSection
    v-if="health.data || error"
    :title="__('Local copy of leads')"
    :description="
      __(
        'The hub keeps a read-only copy of the ERP\'s leads and brings it up to date every minute. The ERP stays the master and is never changed by the copy. Nothing in the hub reads the copy yet.'
      )
    "
  >
    <div
      v-if="error"
      role="alert"
      class="flex flex-wrap items-center gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
    >
      <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
      <span class="min-w-0 flex-1">{{ error }}</span>
      <Button :label="__('Try again')" @click="health.reload()" />
    </div>
    <template v-else-if="health.data">
      <Switch
        :model-value="health.data.enabled"
        :label="__('Keep a local copy of the leads')"
        :description="
          __(
            'Turning it on starts copying every lead in the background. Turning it off stops the updates and keeps what is copied.'
          )
        "
        :disabled="switching"
        @update:model-value="setEnabled"
      />
      <template v-if="health.data.enabled">
        <p
          v-if="health.data.copying"
          class="flex items-center gap-2 text-p-sm text-ink-gray-7"
        >
          <LucideRefreshCw
            class="size-4 shrink-0 animate-spin motion-reduce:animate-none"
            aria-hidden="true"
          />
          <span class="tabular-nums">{{
            __("Copying the leads from the ERP: {0} so far.", [copied])
          }}</span>
        </p>
        <p v-else class="text-p-sm text-ink-gray-7">
          <span class="font-mono tabular-nums">{{ summary }}</span>
        </p>
        <p v-if="comparison" class="text-p-xs text-ink-gray-6">
          {{ comparison }}
        </p>
        <div
          v-if="health.data.last_error"
          role="alert"
          class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
        >
          <LucideCircleAlert
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <span class="min-w-0 flex-1 break-words">{{
            health.data.last_error
          }}</span>
        </div>
        <div class="flex flex-col items-start gap-1.5">
          <Button
            :label="__('Rebuild copy')"
            :loading="rebuilding"
            :disabled="health.data.copying"
            @click="rebuild"
          />
          <p class="text-p-xs text-ink-gray-6">
            {{
              __(
                "Throws the copy away and fills it again from the ERP. Use it if the copy looks wrong; nothing on the ERP changes."
              )
            }}
          </p>
        </div>
      </template>
    </template>
  </SettingsSection>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useIntervalFn } from "@vueuse/core";
import { Button, call, createResource, dayjs, Switch, toast } from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import SettingsSection from "../SettingsSection.vue";

/** helpdesk.api.lead_mirror.get_health */
interface MirrorHealth {
  enabled: boolean;
  copying: boolean;
  leads_copied: number;
  erp_total: number;
  last_synced_on?: string;
  lag_seconds?: number;
  last_error?: string;
  last_compared_on?: string;
  compare_result?: string;
}

const POLL_MS = 5000;

const health = createResource<MirrorHealth>({
  url: "helpdesk.api.lead_mirror.get_health",
  auto: true,
});
const error = computed(() =>
  health.error
    ? errorText(
        health.error,
        __("Couldn't load the local copy's status. Check your connection.")
      )
    : ""
);

const switching = ref(false);
const rebuilding = ref(false);

const copied = computed(() =>
  (health.data?.leads_copied ?? 0).toLocaleString()
);

const summary = computed(() => {
  const data = health.data;
  if (!data) return "";
  const parts = [__("{0} leads copied", [copied.value])];
  parts.push(
    data.last_synced_on
      ? __("last sync {0}", [dayjs(data.last_synced_on).fromNow()])
      : __("not synced yet")
  );
  if (data.last_synced_on) {
    parts.push(__("lag {0} s", [data.lag_seconds ?? 0]));
  }
  return parts.join(" · ");
});

const comparison = computed(() => {
  const data = health.data;
  if (!data?.last_compared_on) return "";
  return `${__("Nightly check {0}", [
    dayjs(data.last_compared_on).fromNow(),
  ])}: ${data.compare_result}`;
});

// while the first copy runs, the count moves
const poll = useIntervalFn(() => health.reload(), POLL_MS, {
  immediate: false,
});
watch(
  () => health.data?.copying,
  (copying) => (copying ? poll.resume() : poll.pause()),
  { immediate: true }
);

async function setEnabled(enabled: boolean) {
  switching.value = true;
  try {
    health.setData(
      await call("helpdesk.api.lead_mirror.set_enabled", { enabled })
    );
  } catch (e) {
    toast.error(errorText(e, __("Couldn't change the local copy.")));
  } finally {
    switching.value = false;
  }
}

async function rebuild() {
  rebuilding.value = true;
  try {
    health.setData(await call("helpdesk.api.lead_mirror.rebuild"));
    toast.success(__("Rebuilding the copy in the background."));
  } catch (e) {
    toast.error(errorText(e, __("Couldn't rebuild the copy.")));
  } finally {
    rebuilding.value = false;
  }
}
</script>
