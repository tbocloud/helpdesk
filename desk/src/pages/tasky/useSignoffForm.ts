import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useDebounceFn } from "@vueuse/core";
import { call, createResource, toast } from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { unfilledPlaceholders, type SignoffQuestion } from "./signoffMeta";

/** A stage's detail: a plain value, or (a table) its rows. */
export type DetailValue = string | number | null | Record<string, unknown>[];

/** What the sign-off form holds; the dialog and the full page share it (docs/project-signoff.md). */
export interface SignoffFormState {
  template: string;
  module_title: string;
  training_date: string;
  trainer: string;
  signatory_contact: string;
  customer_address: string;
  cc: string;
  subject: string;
  body: string;
  attach_pdf: boolean;
  items: SignoffQuestion[];
  /** the stage's details (TBO's Sign-off requirements, Data model): fields and tables */
  details: Record<string, DetailValue>;
}

/** A saved sign-off being edited (Draft or Changes Requested). */
export interface SignoffSource {
  name: string;
  signoff_type?: "Training" | "UAT";
  stage?: string | null;
  template?: string | null;
  module_title?: string | null;
  training_date?: string | null;
  trainer?: string | null;
  signatory_contact?: string | null;
  customer_address?: string | null;
  cc_emails?: string | null;
  email_subject?: string | null;
  email_body?: string | null;
  attach_pdf?: number | boolean;
  details?: Record<string, DetailValue>;
  items: SignoffQuestion[];
}

/** An unsaved form handed from the dialog to the full page (Edit in full page). */
export interface CarriedSignoff {
  form: SignoffFormState;
  baseline: { subject: string; body: string };
  autoFill: boolean;
  pickedType: string;
}

export interface SignoffTemplate {
  name: string;
  template_name: string;
  module?: string;
  signoff_type?: "Training" | "UAT";
  project_type?: string | null;
  stage?: string | null;
  attach_pdf_default?: number;
  /** the template's Always CC, comma separated */
  default_cc?: string | null;
}

export interface SignoffContact {
  contact: string;
  full_name: string;
  email: string;
  designation?: string | null;
  is_primary?: boolean;
}

export interface SignoffAddress {
  name: string;
  title: string;
  type?: string | null;
  is_primary: boolean;
  display: string;
}

/** A detail field as the doctype describes it (get_signoff_form's `fields`). */
export interface DetailField {
  label: string;
  fieldtype: string;
  options?: string[] | null;
  description?: string | null;
  columns?: Record<string, DetailField>;
}

/** A stage of the requirements: its project type, sections, what it needs, what the dialog asks. */
export interface SignoffStage {
  project_type: string;
  sections: string[];
  required: string[];
  dialog: string[];
}

interface FormOptions {
  project_name: string;
  project_type?: string | null;
  customer?: string | null;
  customer_name?: string | null;
  addresses: SignoffAddress[];
  contacts: SignoffContact[];
  default_contact?: string | null;
  default_cc: string[];
  templates: SignoffTemplate[];
  team: { user: string; full_name: string }[];
  can_create_uat: boolean;
  can_send: boolean;
  placeholder_labels: Record<string, string>;
  stages: Record<string, SignoffStage>;
  sections: Record<string, string[]>;
  services: string[];
  platforms: string[];
  erpnext_modules: string[];
  detail_labels: Record<string, string>;
  project_modules: string[];
  fields: Record<string, DetailField>;
}

interface Mail {
  subject: string;
  body: string;
  cc: string[];
}

export const TRAINING_STAGE = "Module Training Sign-off";
const MONTHLY_STAGE = "Monthly Deliverables Sign-off";
const UAT_STAGES = ["UAT Sign-off", "UAT Sign-off and Go-Live"];
// the fields the form keeps outside `details` (they were there before stages)
const OWN_FIELDS = ["training_date", "trainer"];
// a stage-less sign-off (made before stages): a training's
const LEGACY_SECTIONS = ["training"];

function blankForm(): SignoffFormState {
  return {
    template: "",
    module_title: "",
    training_date: "",
    trainer: "",
    signatory_contact: "",
    customer_address: "",
    cc: "",
    subject: "",
    body: "",
    attach_pdf: true,
    items: [],
    details: {},
  };
}

function copyDetails(details: Record<string, DetailValue> = {}) {
  return Object.fromEntries(
    Object.entries(details).map(([k, v]) => [
      k,
      Array.isArray(v) ? v.map((row) => ({ ...row })) : v,
    ])
  );
}

/** The words of an HTML body, so the editor tidying its markup isn't "changed by hand". */
export function mailWords(html: string) {
  const text =
    new DOMParser().parseFromString(html || "", "text/html").body.textContent ||
    "";
  return text.replace(/\s+/g, " ").trim();
}

export function splitEmails(text: string) {
  return text
    .split(/[,;\s]+/)
    .map((e) => e.trim())
    .filter(Boolean);
}

/** "Social Media, SEO" as a list, and back. */
export function splitChoices(text: unknown): string[] {
  return String(text || "")
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

function isoDate(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * The New sign-off form: the project's choices, the stage's details, the mail filled in from
 * the template until it is written by hand, why it can't be sent yet, and saving or sending
 * it. `withQuestions` (the full page) also edits the questions, starting from the template's.
 */
export function useSignoffForm(opts: {
  projectId: () => string;
  lead?: () => string | null | undefined;
  uat: () => boolean;
  signoff?: () => SignoffSource | null | undefined;
  withQuestions?: boolean;
}) {
  const form = reactive<SignoffFormState>(blankForm());
  const editing = computed(() => !!opts.signoff?.());
  const errorMessage = ref("");

  // the mail as last filled in; it follows the choices until it is written by hand
  const baseline = ref({ subject: "", body: "" });
  const autoFill = ref(true);
  const previewing = ref(false);
  const mailError = ref("");
  const confirmReapply = ref(false);
  // who the current template copies, so a template picked instead takes them off again
  let templateCc: string[] = [];
  // the questions came from the template, so another template may replace them
  const questionsFromTemplate = ref(true);
  // carried over from the dialog: keep it exactly as it was typed
  let carried = false;

  const options = createResource({
    url: "helpdesk.api.project_signoff.get_signoff_form",
    makeParams: () => ({
      project: opts.projectId(),
      lead: opts.lead?.() || null,
    }),
    onSuccess(data: FormOptions) {
      if (editing.value || carried) {
        if (editing.value) {
          // its template's Always CC is in the draft's CC: a template picked instead replaces it
          const own = data.templates.find((t) => t.name === form.template);
          templateCc = (own?.default_cc ?? "").split(/[,;\s]+/).filter(Boolean);
          // a draft made before mails were kept starts from its template's
          if (form.subject) followIfUntouched();
          else refreshMail(true);
        }
        return;
      }
      form.cc = data.default_cc.join(", ");
      form.signatory_contact = data.default_contact || "";
      form.customer_address = data.addresses[0]?.name ?? "";
      // a UAT starts on the first UAT template that fits the project, if any
      if (opts.uat()) form.template = fitting.value[0]?.name ?? "";
      applyTemplate();
      refreshMail(true);
    },
  });
  const data = computed(() => options.data as FormOptions | undefined);

  /** Start the form: from a saved sign-off, from the dialog's unsaved one, or blank. */
  function start(from?: CarriedSignoff | null) {
    errorMessage.value = "";
    mailError.value = "";
    confirmReapply.value = false;
    templateCc = [];
    carried = !!from;
    const s = opts.signoff?.();
    if (from) {
      Object.assign(form, {
        ...from.form,
        items: from.form.items.slice(),
        details: copyDetails(from.form.details),
      });
      baseline.value = { ...from.baseline };
      autoFill.value = from.autoFill;
      pickedType.value = from.pickedType;
    } else {
      Object.assign(form, blankForm(), {
        template: s?.template ?? "",
        module_title: s?.module_title ?? "",
        training_date: s?.training_date ?? "",
        trainer: s?.trainer ?? "",
        signatory_contact: s?.signatory_contact ?? "",
        customer_address: s?.customer_address ?? "",
        cc: s?.cc_emails ?? "",
        subject: s?.email_subject ?? "",
        body: s?.email_body ?? "",
        attach_pdf: s ? !!s.attach_pdf : true,
        items: s ? s.items.map((i) => ({ ...i })) : [],
        details: copyDetails(s?.details),
      });
      baseline.value = { subject: form.subject, body: form.body };
      // a draft's own mail is kept; only a new one follows the template
      autoFill.value = !s?.email_subject;
      pickedType.value = "";
    }
    questionsFromTemplate.value = !s && !from;
    options.reload();
  }

  /** What the dialog hands to the full page: everything typed, nothing saved. */
  function carry(): CarriedSignoff {
    return {
      form: {
        ...form,
        items: form.items.map((i) => ({ ...i })),
        details: copyDetails(form.details),
      },
      baseline: { ...baseline.value },
      autoFill: autoFill.value,
      pickedType: pickedType.value,
    };
  }

  // a project without a type: picked here to narrow the templates (the project is unchanged)
  const pickedType = ref("");
  const projectType = computed(
    () => data.value?.project_type || pickedType.value
  );

  // a new UAT from the plan offers the UAT templates; otherwise every template of the
  // project's type (or of any type), whatever its stage
  const fitting = computed<SignoffTemplate[]>(() => {
    const type = projectType.value;
    return (data.value?.templates ?? []).filter(
      (t) =>
        (!opts.uat() || t.signoff_type === "UAT") &&
        (!t.project_type || !type || t.project_type === type)
    );
  });
  const template = computed(() =>
    (data.value?.templates ?? []).find((t) => t.name === form.template)
  );
  const templateOptions = computed(() => [
    ...fitting.value.map((t) => ({ label: t.template_name, value: t.name })),
    {
      label: opts.uat()
        ? __("No template: the standard UAT mail")
        : __("No template: start empty"),
      value: "",
    },
  ]);

  // ---------- the stage: which details show, which are needed ----------

  /** The stage, from the template picked (a saved sign-off keeps its own). */
  const stage = computed(
    () => opts.signoff?.()?.stage || template.value?.stage || ""
  );
  const stageInfo = computed(() =>
    stage.value ? data.value?.stages[stage.value] : undefined
  );
  const isUat = computed(
    () =>
      opts.uat() ||
      opts.signoff?.()?.signoff_type === "UAT" ||
      template.value?.signoff_type === "UAT"
  );
  /** A UAT whose tests come from the plan's SRS (New UAT sign-off). */
  const fromPlan = computed(() => opts.uat());
  /** A training: the Module Training stage, or a stage-less training made before stages. */
  const isTraining = computed(
    () => !isUat.value && (!stage.value || stage.value === TRAINING_STAGE)
  );
  /** The sections the stage shows (ad spend on a month's deliverables only with Paid Ads). */
  const shownSections = computed<string[]>(() => {
    if (!stageInfo.value) return isTraining.value ? LEGACY_SECTIONS : [];
    const services = splitChoices(form.details.services);
    return stageInfo.value.sections.filter(
      (s) =>
        !(
          s === "ad_spend" &&
          stage.value === MONTHLY_STAGE &&
          !services.includes("Paid Ads")
        )
    );
  });
  /** Every detail of the shown sections, once each, in order (the full page). */
  const shownFields = computed<string[]>(() => [
    ...new Set(
      shownSections.value.flatMap((s) => data.value?.sections[s] ?? [])
    ),
  ]);
  /** The details the dialog asks for; the rest are on the full page. */
  const dialogFields = computed<string[]>(() =>
    stageInfo.value
      ? stageInfo.value.dialog
      : isTraining.value
      ? OWN_FIELDS
      : []
  );
  /** A stage-less training names its module in words; a stage picks modules. */
  const namesModule = computed(() => isTraining.value && !stage.value);

  function detail(field: string): DetailValue {
    return OWN_FIELDS.includes(field)
      ? (form as unknown as Record<string, string>)[field]
      : form.details[field] ?? null;
  }
  function setDetail(field: string, value: DetailValue) {
    if (OWN_FIELDS.includes(field))
      (form as unknown as Record<string, unknown>)[field] = value ?? "";
    else form.details[field] = value;
  }
  function filled(field: string) {
    const value = detail(field);
    if (Array.isArray(value))
      return value.some((row) =>
        Object.values(row).some((v) => String(v ?? "").trim())
      );
    return String(value ?? "").trim() !== "";
  }
  const missingDetails = computed(() =>
    (stageInfo.value?.required ?? [])
      .filter((field) => !filled(field))
      .map((field) => data.value?.detail_labels[field] || field)
  );

  /** A template's own starting point: its attach default, its module, and the stage's
   * defaults (the ERPNext version, last month for a month's deliverables, a UAT's modules). */
  function applyTemplate() {
    const t = template.value;
    if (t && t.attach_pdf_default !== undefined)
      form.attach_pdf = !!t.attach_pdf_default;
    if (t?.module && namesModule.value && !form.module_title.trim())
      form.module_title = t.module;
    const kind = stageInfo.value?.project_type;
    if (kind === "ERP Implementation" && !form.details.erpnext_version)
      form.details.erpnext_version = "V16";
    const modules = (form.details.modules as Record<string, unknown>[]) || [];
    if (!modules.length) {
      const names =
        stage.value === TRAINING_STAGE && t?.module
          ? [t.module]
          : UAT_STAGES.includes(stage.value)
          ? data.value?.project_modules ?? []
          : [];
      if (names.length)
        form.details.modules = names.map((module) => ({
          module,
          processes_covered: "",
          status: "Completed",
          remarks: "",
        }));
    }
    if (stage.value === MONTHLY_STAGE && !form.details.period_from) {
      const now = new Date();
      form.details.period_from = isoDate(
        new Date(now.getFullYear(), now.getMonth() - 1, 1)
      );
      form.details.period_to = isoDate(
        new Date(now.getFullYear(), now.getMonth(), 0)
      );
    }
  }

  const trainerOptions = computed(() =>
    (data.value?.team ?? []).map((m) => ({
      label: m.full_name || m.user,
      value: m.user,
      description: m.user,
    }))
  );
  const contacts = computed<SignoffContact[]>(() => data.value?.contacts ?? []);
  const contactOptions = computed(() =>
    contacts.value.map((c) => ({
      label: c.full_name,
      value: c.contact,
      description: [c.designation, c.email].filter(Boolean).join(" · "),
    }))
  );
  const signatory = computed(() =>
    contacts.value.find((c) => c.contact === form.signatory_contact)
  );
  const addresses = computed<SignoffAddress[]>(
    () => data.value?.addresses ?? []
  );
  const address = computed(() =>
    addresses.value.find((a) => a.name === form.customer_address)
  );
  const ccList = computed(() => splitEmails(form.cc));

  function onTemplate() {
    applyTemplate();
    if (questionsFromTemplate.value) loadTemplateQuestions();
  }

  /** The full page shows the template's questions to edit before saving (a UAT's from the
   * plan come from the SRS when it is saved). */
  async function loadTemplateQuestions() {
    if (!opts.withQuestions || editing.value || opts.uat()) return;
    if (!form.template) {
      form.items = [];
      return;
    }
    try {
      form.items = await call(
        "helpdesk.api.project_signoff.get_template_questions",
        {
          project: opts.projectId(),
          template: form.template,
          lead: opts.lead?.() || null,
        }
      );
    } catch (e) {
      toast.error(errorText(e, __("Couldn't load the template's questions.")));
    }
  }
  /** Questions changed by hand: another template no longer replaces them. */
  function setItems(items: SignoffQuestion[]) {
    form.items = items;
    questionsFromTemplate.value = false;
  }

  /** A month's (or a campaign's) deliverables from the content calendar. */
  const pulling = ref(false);
  async function pullDeliverables() {
    if (!form.details.period_from || !form.details.period_to) {
      toast.error(__("Set the period first."));
      return;
    }
    pulling.value = true;
    try {
      const rows = await call(
        "helpdesk.api.project_signoff.get_signoff_deliverables",
        {
          project: opts.projectId(),
          period_from: form.details.period_from,
          period_to: form.details.period_to,
          lead: opts.lead?.() || null,
        }
      );
      if (!rows.length)
        toast.info(__("No posts in the content calendar for the period."));
      else form.details.deliverables = rows;
    } catch (e) {
      toast.error(errorText(e, __("Couldn't read the content calendar.")));
    } finally {
      pulling.value = false;
    }
  }

  /** The details as the API takes them: the shown ones, with the trainer's and the date. */
  function detailPayload() {
    return {
      ...copyDetails(form.details),
      training_date: form.training_date || null,
      trainer: form.trainer || null,
    };
  }

  // ---------- the mail: filled in from the template, until it is changed by hand ----------

  const mailEdited = computed(
    () =>
      form.subject.trim() !== baseline.value.subject.trim() ||
      mailWords(form.body) !== mailWords(baseline.value.body)
  );

  // an answer for older choices must not land over the newest one
  let asked = 0;

  function mailParams() {
    return {
      project: opts.projectId(),
      signoff_type: isUat.value ? "UAT" : "Training",
      template: form.template || null,
      signatory_contact: form.signatory_contact || null,
      module_title: form.module_title,
      training_date: form.training_date || null,
      trainer: form.trainer || null,
      customer_address: form.customer_address || null,
      details: detailPayload(),
      lead: opts.lead?.() || null,
    };
  }

  /** A draft's kept mail that is still exactly what its choices fill in was never written by
   * hand: it goes on following them (a date set later fills in, a new signatory is greeted). */
  async function followIfUntouched() {
    try {
      const mail: Mail = await call(
        "helpdesk.api.project_signoff.preview_signoff_mail",
        mailParams()
      );
      if (
        mail.subject.trim() === form.subject.trim() &&
        mailWords(mail.body) === mailWords(form.body)
      )
        autoFill.value = true;
    } catch {
      // the draft keeps its mail; Reapply template is there
    }
  }
  async function refreshMail(force = false) {
    if (!data.value?.customer) return;
    if (!force && (!autoFill.value || mailEdited.value)) return;
    const ask = ++asked;
    previewing.value = true;
    mailError.value = "";
    try {
      const mail: Mail = await call(
        "helpdesk.api.project_signoff.preview_signoff_mail",
        mailParams()
      );
      // typed into while it was being filled: what was typed stays
      if (ask !== asked || (!force && mailEdited.value)) return;
      form.subject = mail.subject;
      form.body = mail.body;
      baseline.value = { subject: mail.subject, body: mail.body };
      autoFill.value = true;
      // the template's own CC join who is already copied, replacing an earlier template's
      const earlier = new Set(templateCc.map((e) => e.toLowerCase()));
      const kept = ccList.value.filter((e) => !earlier.has(e.toLowerCase()));
      const cc = new Set(kept.map((e) => e.toLowerCase()));
      form.cc = [
        ...kept,
        ...mail.cc.filter((e) => !cc.has(e.toLowerCase())),
      ].join(", ");
      templateCc = mail.cc;
    } catch (e) {
      if (ask === asked)
        mailError.value = errorText(e, __("Couldn't fill in the mail."));
    } finally {
      if (ask === asked) previewing.value = false;
    }
  }
  const refreshSoon = useDebounceFn(() => refreshMail(), 400);
  watch(
    () =>
      JSON.stringify([
        form.template,
        form.signatory_contact,
        form.module_title,
        form.training_date,
        form.trainer,
        form.customer_address,
        form.details,
      ]),
    () => data.value && refreshSoon()
  );

  function reapply() {
    confirmReapply.value = false;
    refreshMail(true);
  }
  // words written by hand are lost: asked first; a kept draft mail isn't anyone's typing
  function askReapply() {
    if (mailEdited.value) confirmReapply.value = true;
    else reapply();
  }

  /** What the mail still needs, in the words of the fields that fill it. */
  const unfilled = computed(() =>
    unfilledPlaceholders(`${form.subject} ${form.body}`).map(
      (name) => data.value?.placeholder_labels[name] || `{{ ${name} }}`
    )
  );

  // ---------- saving and sending ----------

  // who signs and what the stage needs: until they are given, the mail's gaps are theirs
  const detailsPicked = computed(
    () => !!form.signatory_contact && !missingDetails.value.length
  );

  /** Why it can't be sent yet, in words; "" when it can (the requirements' checks). */
  const sendBlocked = computed(() => {
    if (!data.value?.customer) return __("This project has no customer.");
    if (!form.signatory_contact)
      return __("Pick who signs off for the customer.");
    if (namesModule.value && !form.module_title.trim())
      return __("Name the module, e.g. Accounts.");
    if (namesModule.value && !form.trainer) return __("Pick the trainer.");
    if (opts.uat() && !form.trainer)
      return __("Pick who tests with the client.");
    if (missingDetails.value.length)
      return __(
        "Fill {0}: the {1} needs it.",
        missingDetails.value.join(", "),
        __(stage.value)
      );
    const bad = ccList.value.find((e) => !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e));
    if (bad) return __("{0} isn't a valid email address.", bad);
    if (previewing.value) return __("Filling in the mail…");
    if (!form.subject.trim() || !mailWords(form.body))
      return __("Write the mail's subject and message.");
    if (unfilled.value.length)
      return __("Fill {0}: it is used in the mail.", unfilled.value.join(", "));
    if (
      form.body.includes("sign_off_link") &&
      opts.withQuestions &&
      !opts.uat() &&
      !form.items.some((i) => i.question.trim())
    )
      return __(
        "The mail links to the questions page, but there are no questions."
      );
    return "";
  });

  const saving = ref<"" | "draft" | "send">("");

  /** Save (or `send`): the sign-off's name, or null when it didn't go through (the form
   * keeps what was typed and says why). */
  async function submit(send: boolean): Promise<string | null> {
    if (!form.signatory_contact) {
      errorMessage.value = __("Pick who signs off for the customer.");
      return null;
    }
    if (opts.uat() && !form.trainer) {
      errorMessage.value = __("Pick who tests with the client.");
      return null;
    }
    if (namesModule.value && !form.module_title.trim()) {
      errorMessage.value = __("Name the module, e.g. Accounts.");
      return null;
    }
    if (!form.items.every((i) => i.question.trim())) {
      errorMessage.value = __("Give every question some text, or remove it.");
      return null;
    }
    errorMessage.value = "";
    const mail = {
      email_subject: form.subject.trim(),
      email_body: mailWords(form.body) ? form.body : "",
      cc_emails: ccList.value.join(", "),
      customer_address: form.customer_address || null,
      attach_pdf: form.attach_pdf ? 1 : 0,
      details: detailPayload(),
    };
    const common = {
      module_title: form.module_title.trim(),
      training_date: form.training_date || null,
      trainer: form.trainer,
      signatory_contact: form.signatory_contact,
    };
    const how = { send: send ? 1 : 0, lead: opts.lead?.() || null };
    const signoff = opts.signoff?.();
    saving.value = send ? "send" : "draft";
    try {
      let name: string;
      if (signoff) {
        await call("helpdesk.api.project_signoff.update_signoff", {
          signoff: signoff.name,
          items: form.items,
          ...common,
          ...mail,
        });
        if (send)
          await call("helpdesk.api.project_signoff.send_signoff", {
            signoff: signoff.name,
          });
        name = signoff.name;
      } else if (opts.uat()) {
        name = (
          await call("helpdesk.api.project_signoff.create_uat_signoff", {
            project: opts.projectId(),
            trainer: form.trainer,
            signatory_contact: form.signatory_contact,
            template: form.template || null,
            ...mail,
            ...how,
          })
        ).name;
      } else {
        name = (
          await call("helpdesk.api.project_signoff.create_signoff", {
            project: opts.projectId(),
            template: form.template || null,
            items: opts.withQuestions ? form.items : null,
            ...common,
            ...mail,
            ...how,
          })
        ).name;
      }
      toast.success(
        send
          ? __("Sent to {0}", signatory.value?.full_name || "")
          : signoff
          ? __("Sign-off saved")
          : __("Saved as a draft")
      );
      return name;
    } catch (e) {
      // nothing was sent: what was typed stays, to fix and send again
      errorMessage.value = errorText(
        e,
        send
          ? __("Couldn't send the sign-off.")
          : __("Couldn't save the sign-off.")
      );
      return null;
    } finally {
      saving.value = "";
    }
  }

  return reactive({
    form,
    options,
    data,
    editing,
    isUat,
    fromPlan,
    isTraining,
    namesModule,
    stage,
    shownSections,
    shownFields,
    dialogFields,
    missingDetails,
    pickedType,
    projectType,
    errorMessage,
    previewing,
    mailError,
    confirmReapply,
    mailEdited,
    fitting,
    templateOptions,
    trainerOptions,
    contacts,
    contactOptions,
    signatory,
    addresses,
    address,
    ccList,
    unfilled,
    detailsPicked,
    sendBlocked,
    saving,
    pulling,
    start,
    carry,
    onTemplate,
    setItems,
    detail,
    setDetail,
    detailPayload,
    pullDeliverables,
    reapply,
    askReapply,
    autoFill,
    submit,
  });
}

export type SignoffForm = ReturnType<typeof useSignoffForm>;
