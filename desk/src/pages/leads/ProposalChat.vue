<template>
  <!-- the guided start: scripted questions (no AI), quick replies for fixed choices; the AI only
       reads the website and the client's needs. Every answer lands in the summary beside it. -->
  <section
    class="flex min-h-0 flex-col rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-labelledby="titleId"
  >
    <div
      class="flex items-center gap-2 border-b border-outline-gray-1 px-4 py-3"
    >
      <h2 :id="titleId" class="text-base-medium text-ink-gray-9">
        {{ __("Proposal assistant") }}
      </h2>
      <span class="text-p-sm tabular-nums text-ink-gray-5">
        {{
          __(
            "{0} of {1}",
            String(Math.min(step + 1, STEPS.length)),
            String(STEPS.length)
          )
        }}
      </span>
      <Button
        class="ml-auto"
        variant="ghost"
        :label="__('Skip to the form')"
        @click="emit('skip')"
      />
    </div>

    <ol
      ref="logEl"
      class="flex min-h-[16rem] flex-1 flex-col gap-3 overflow-y-auto px-4 py-4"
      role="log"
      aria-live="polite"
      :aria-label="__('Conversation')"
    >
      <li
        v-for="(m, i) in props.log"
        :key="i"
        class="max-w-[85%] rounded-lg px-3 py-2 text-p-sm"
        :class="
          m.role === 'assistant'
            ? 'self-start bg-surface-gray-1 text-ink-gray-8'
            : 'self-end border border-outline-gray-2 bg-surface-base text-ink-gray-9'
        "
      >
        <span class="sr-only">{{
          m.role === "assistant" ? __("Assistant:") : __("You:")
        }}</span>
        <span class="whitespace-pre-line">{{ m.text }}</span>
      </li>
      <li v-if="busy" class="self-start text-p-sm text-ink-gray-5">
        {{ busyText }}
      </li>
    </ol>

    <div class="flex flex-col gap-3 border-t border-outline-gray-1 p-4">
      <template v-if="current">
        <div
          v-if="chips.length"
          class="flex flex-wrap gap-2"
          role="group"
          :aria-label="__('Quick replies')"
        >
          <button
            v-for="c in chips"
            :key="c.value"
            type="button"
            :aria-pressed="current.multi ? picked.includes(c.value) : undefined"
            :disabled="busy"
            class="inline-flex min-h-[36px] items-center gap-1.5 rounded-full border px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight disabled:opacity-60"
            :class="
              current.multi && picked.includes(c.value)
                ? 'border-transparent bg-brand text-brand-on'
                : 'border-outline-gray-2 bg-surface-base text-ink-gray-8 hover:bg-surface-gray-1'
            "
            @click="chip(c.value)"
          >
            <LucideCheck
              v-if="current.multi && picked.includes(c.value)"
              class="size-3.5"
              aria-hidden="true"
            />
            {{ c.label }}
          </button>
        </div>
        <form
          v-if="current.input"
          class="flex items-end gap-2"
          @submit.prevent="answerText"
        >
          <FormControl
            v-model="draft"
            class="flex-1"
            :type="current.input"
            :rows="current.input === 'textarea' ? 3 : undefined"
            :aria-label="current.ask"
            :placeholder="current.placeholder"
            :disabled="busy"
            @keydown.enter.exact="
              current.input === 'textarea' && submitOnEnter($event)
            "
          />
          <Button
            type="submit"
            variant="solid"
            :label="__('Send')"
            :disabled="busy || !draft.trim()"
          >
            <template #icon>
              <LucideArrowUp class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </form>
        <div v-if="current.multi" class="flex justify-end">
          <Button :label="__('Done')" :disabled="busy" @click="finishMulti" />
        </div>
      </template>
      <div v-else class="flex flex-wrap items-center gap-3">
        <p class="text-p-sm text-ink-gray-7">
          {{ __("That's everything. Check the summary, then generate.") }}
        </p>
        <Button
          class="ml-auto"
          variant="solid"
          :label="__('Generate proposal')"
          :disabled="!canGenerate"
          :loading="generating"
          @click="emit('generate')"
        />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, call, FormControl } from "frappe-ui";
import { computed, nextTick, onMounted, ref, useId } from "vue";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucideCheck from "~icons/lucide/check";
import {
  emptyScoping,
  suggestTimeline,
  suits,
  type ClientProfile,
  type ProposalOptions,
  type Scoping,
} from "./proposals";

/** What the chat fills: the same state as the summary form beside it. */
export interface ChatState {
  template: string;
  profile: ClientProfile;
  requirements: string;
  scoping: Scoping;
}
export interface ChatLine {
  role: "assistant" | "presales";
  text: string;
}

// the parent's reactive state and log, changed in place: several answers can land in one tick
const props = defineProps<{
  lead: string;
  options: ProposalOptions;
  canGenerate: boolean;
  generating?: boolean;
  state: ChatState;
  log: ChatLine[];
}>();
const emit = defineEmits<{ (e: "skip"): void; (e: "generate"): void }>();

const titleId = `proposal-chat-${useId()}`;
const logEl = ref<HTMLElement>();
const step = ref(0);
const draft = ref("");
const picked = ref<string[]>([]);
const busy = ref(false);
const busyText = ref("");

interface Step {
  key: string;
  ask: () => string;
  input?: "text" | "textarea" | "number";
  placeholder?: string;
  multi?: boolean;
  chips?: () => { label: string; value: string }[];
  /** skip the step when it has nothing to ask */
  when?: () => boolean;
  onChip?: (value: string) => Promise<void> | void;
  onText?: (text: string) => Promise<void> | void;
  onDone?: (values: string[]) => void;
}

const ai = computed(() => !!props.options.ai);
const template = computed(() =>
  props.options.templates?.find((t) => t.name === props.state.template)
);
const solution = computed(() => template.value?.solution_type);
const sc = () => props.state.scoping;
function setScoping(patch: Partial<Scoping>) {
  Object.assign(props.state.scoping, patch);
}
function setProfile(patch: Partial<ClientProfile>) {
  Object.assign(props.state.profile, patch);
}
function say(text: string, role: ChatLine["role"] = "assistant") {
  props.log.push({ role, text });
  nextTick(() => logEl.value?.scrollTo({ top: logEl.value.scrollHeight }));
}

async function work<T>(text: string, run: () => Promise<T>): Promise<T | null> {
  busy.value = true;
  busyText.value = text;
  try {
    return await run();
  } catch (e) {
    say(errorText(e, __("That didn't work. Type it in the summary instead.")));
    return null;
  } finally {
    busy.value = false;
  }
}

const STEPS: Step[] = [
  {
    key: "website",
    ask: () =>
      ai.value
        ? __("What's the client's website? I'll read it to fill their profile.")
        : __("What's the client's website?"),
    input: "text",
    placeholder: "client.example",
    chips: () => [{ label: __("No website"), value: "none" }],
    onChip: () => {},
    onText: async (typed) => {
      const url = /^https?:\/\//i.test(typed) ? typed : `https://${typed}`;
      setProfile({ website: url });
      if (!ai.value) return;
      const read = await work(__("Reading the website…"), () =>
        call("helpdesk.api.proposals.read_client_website", {
          lead: props.lead,
          url,
        })
      );
      const p = (read as { profile?: Partial<ClientProfile> } | null)?.profile;
      if (!p) return;
      const filled: Partial<ClientProfile> = {};
      for (const [k, v] of Object.entries(p))
        if (v && k in props.state.profile) filled[k as keyof ClientProfile] = v;
      setProfile(filled);
      say(
        [
          p.about && __("They: {0}", p.about),
          p.industry && __("Industry: {0}", p.industry),
          p.locations && __("Locations: {0}", p.locations),
        ]
          .filter(Boolean)
          .join("\n") || __("The site had little to go on.")
      );
    },
  },
  {
    key: "industry",
    ask: () => __("What industry are they in?"),
    input: "text",
    when: () => !props.state.profile.industry.trim(),
    onText: (text) => setProfile({ industry: text }),
  },
  {
    key: "needs",
    ask: () =>
      __(
        "What does the client need, and what hurts today? Type or paste it, or use the lead's notes."
      ),
    input: "textarea",
    chips: () => [{ label: __("Use the lead's notes"), value: "notes" }],
    onChip: async () => {
      const got = await work(__("Reading the lead's notes…"), () =>
        call("helpdesk.api.proposals.get_requirements_from_lead", {
          lead: props.lead,
        })
      );
      const text = (got as { text?: string } | null)?.text || "";
      if (!text) {
        say(__("The lead has no notes yet. Type it instead."));
        throw new Error("no notes");
      }
      await takeNeeds(text, false);
    },
    onText: (text) => takeNeeds(text, true),
  },
  {
    key: "modules",
    ask: () =>
      __("Which modules? The usual ones for this kind of project are picked."),
    multi: true,
    chips: () =>
      (props.options.catalogue ?? [])
        .filter((m) => suits(m.solution_types, solution.value))
        .map((m) => ({ label: m.module_name, value: m.module_name })),
    onDone: (values) => setScoping({ modules: values }),
  },
  {
    key: "customisations",
    ask: () =>
      __(
        "Any customisations? One short line each, like “salary slip in our format”."
      ),
    input: "textarea",
    chips: () => [{ label: __("None"), value: "none" }],
    onChip: () => setScoping({ customisation: false, customisations: [] }),
    onText: (text) => {
      const items = text
        .split(/\n|;/)
        .map((l) => l.replace(/^[-•\d.)\s]+/, "").trim())
        .filter(Boolean);
      const list = [
        ...sc().customisations,
        ...items.map((item) => ({ item, days: 1 })),
      ];
      setScoping({ customisation: list.length > 0, customisations: list });
    },
  },
  {
    key: "extras",
    ask: () => __("Does it include any of these?"),
    multi: true,
    chips: () => [
      { label: __("Mobile app"), value: "mobile_app" },
      { label: __("Data migration"), value: "data_migration" },
      { label: __("Integrations"), value: "integrations" },
      { label: __("Source code handed over"), value: "source_code" },
    ],
    onDone: (values) => {
      setScoping({
        mobile_app: values.includes("mobile_app"),
        data_migration: values.includes("data_migration"),
        source_code: values.includes("source_code"),
        integrations: values.includes("integrations")
          ? sc().integrations || " "
          : "",
      });
    },
  },
  {
    key: "integrations",
    ask: () => __("Which systems should it connect to?"),
    input: "text",
    when: () => !!sc().integrations,
    onText: (text) => setScoping({ integrations: text }),
  },
  {
    key: "users",
    ask: () => __("About how many users?"),
    input: "number",
    chips: () => ["10", "25", "50", "100"].map((n) => ({ label: n, value: n })),
    onChip: (n) => setScoping({ users: Number(n) }),
    onText: (text) => setScoping({ users: parseInt(text, 10) || 0 }),
  },
  {
    key: "hosting",
    ask: () => __("Where will it be hosted?"),
    chips: () => [
      ...(props.options.hosting ?? []).map((h) => ({ label: __(h), value: h })),
      { label: __("Not decided"), value: "" },
    ],
    onChip: (h) => setScoping({ hosting: h || null }),
  },
  {
    key: "timeline",
    ask: () =>
      __(
        "Which timeline? I suggest {0} from the effort.",
        suggested.value || "–"
      ),
    chips: () =>
      (props.options.timelines ?? []).map((t) => ({
        label:
          t.title === suggested.value
            ? __("{0} (suggested)", t.title)
            : t.title,
        value: t.title,
      })),
    onChip: (t) => setScoping({ timeline_template: t }),
  },
  {
    key: "payment",
    ask: () => __("Which payment terms?"),
    chips: () =>
      (props.options.payment_terms ?? []).map((t) => ({ label: t, value: t })),
    onChip: (t) => setScoping({ payment_terms: t }),
  },
  {
    key: "amc",
    ask: () => __("An AMC to recommend?"),
    chips: () => [
      ...(props.options.amc_plans ?? []).map((p) => ({ label: p, value: p })),
      { label: __("No AMC"), value: "" },
    ],
    onChip: (p) => setScoping({ amc: !!p, amc_plan: p || null }),
  },
  {
    key: "else",
    ask: () => __("Anything else the proposal should say?"),
    input: "textarea",
    chips: () => [{ label: __("Nothing else"), value: "none" }],
    onChip: () => {},
    onText: (text) => {
      props.state.requirements = [props.state.requirements, text]
        .filter(Boolean)
        .join("\n\n");
    },
  },
];

const suggested = computed(() =>
  suggestTimeline(
    props.options.timelines ?? [],
    sc(),
    props.options.catalogue ?? []
  )
);
const current = computed(() => STEPS[step.value]);
const chips = computed(() => current.value?.chips?.() ?? []);

/** The needs text: kept, and with the AI read into the form (the one extraction call). */
async function takeNeeds(text: string, typed: boolean) {
  const requirements = typed
    ? text
    : [props.state.requirements, text].filter(Boolean).join("\n\n");
  props.state.requirements = requirements;
  if (!props.state.profile.pain_points.trim())
    setProfile({ pain_points: text.slice(0, 1000) });
  if (!ai.value) return;
  const form = (await work(__("Reading the requirements…"), () =>
    call("helpdesk.api.proposals.extract_requirements", {
      lead: props.lead,
      text: requirements,
    })
  )) as { template?: string | null; scoping?: Scoping } | null;
  if (!form?.scoping) return;
  if (form.template) props.state.template = form.template;
  props.state.scoping = { ...emptyScoping(), ...sc(), ...form.scoping };
  const s = form.scoping;
  say(
    [
      form.template && __("Template: {0}", form.template),
      s.modules.length && __("Modules: {0}", s.modules.join(", ")),
      s.customisations.length &&
        __(
          "Customisations: {0}",
          s.customisations.map((c) => c.item).join("; ")
        ),
      s.users && __("Users: {0}", String(s.users)),
    ]
      .filter(Boolean)
      .join("\n") || __("Noted. Nothing to fill from it yet.")
  );
}

function ask() {
  while (current.value?.when && !current.value.when()) step.value++;
  if (!current.value) {
    say(
      __(
        "That's everything. Check the summary on the right; edit anything there."
      )
    );
    return;
  }
  picked.value =
    current.value.key === "modules"
      ? [...sc().modules]
      : current.value.key === "extras"
      ? (["mobile_app", "data_migration", "source_code"] as const)
          .filter((k) => sc()[k])
          .concat(sc().integrations ? ["integrations"] : [])
      : [];
  say(current.value.ask());
}

function next() {
  draft.value = "";
  step.value++;
  ask();
}

async function chip(value: string) {
  const s = current.value;
  if (!s || busy.value) return;
  if (s.multi) {
    picked.value = picked.value.includes(value)
      ? picked.value.filter((v) => v !== value)
      : [...picked.value, value];
    return;
  }
  say(chips.value.find((c) => c.value === value)?.label || value, "presales");
  try {
    await s.onChip?.(value);
  } catch {
    return;
  }
  next();
}

async function answerText() {
  const s = current.value;
  const text = draft.value.trim();
  if (!s || !text || busy.value) return;
  say(text, "presales");
  draft.value = "";
  await s.onText?.(text);
  next();
}

function finishMulti() {
  const s = current.value;
  if (!s) return;
  const labels = chips.value
    .filter((c) => picked.value.includes(c.value))
    .map((c) => c.label);
  say(labels.join(", ") || __("None"), "presales");
  s.onDone?.(picked.value);
  next();
}

function submitOnEnter(event: KeyboardEvent) {
  event.preventDefault();
  answerText();
}

onMounted(() => {
  if (!props.log.length) ask();
});
</script>
