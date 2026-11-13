import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useDebounceFn } from "@vueuse/core";
import { call, createResource, toast } from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { unfilledPlaceholders, type SignoffQuestion } from "./signoffMeta";

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
}

/** A saved sign-off being edited (Draft or Changes Requested). */
export interface SignoffSource {
  name: string;
  signoff_type?: "Training" | "UAT";
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
  items: SignoffQuestion[];
}

/** An unsaved form handed from the dialog to the full page (Edit in full page). */
export interface CarriedSignoff {
  form: SignoffFormState;
  baseline: { subject: string; body: string };
  autoFill: boolean;
}

export interface SignoffTemplate {
  name: string;
  template_name: string;
  module?: string;
  signoff_type?: "Training" | "UAT";
  project_type?: string | null;
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
}

interface Mail {
  subject: string;
  body: string;
  cc: string[];
}

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
  };
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

/**
 * The New sign-off form: the project's choices, the mail filled in from the template until it
 * is written by hand, why it can't be sent yet, and saving or sending it. `withQuestions`
 * (the full page) also edits the questions, starting from the template's.
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
  const isUat = computed(
    () => opts.uat() || opts.signoff?.()?.signoff_type === "UAT"
  );
  const errorMessage = ref("");

  // the mail as last filled in; it follows the choices until it is written by hand
  const baseline = ref({ subject: "", body: "" });
  const autoFill = ref(true);
  const previewing = ref(false);
  const mailError = ref("");
  const confirmReapply = ref(false);
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
        // a draft made before mails were kept starts from its template's
        if (editing.value && !form.subject) refreshMail(true);
        return;
      }
      form.cc = data.default_cc.join(", ");
      form.signatory_contact = data.default_contact || "";
      form.customer_address = data.addresses[0]?.name ?? "";
      // a UAT starts on the first UAT template that fits the project, if any
      if (isUat.value) form.template = fitting.value[0]?.name ?? "";
      refreshMail(true);
      if (form.template) loadTemplateQuestions();
    },
  });
  const data = computed(() => options.data as FormOptions | undefined);

  /** Start the form: from a saved sign-off, from the dialog's unsaved one, or blank. */
  function start(from?: CarriedSignoff | null) {
    errorMessage.value = "";
    mailError.value = "";
    confirmReapply.value = false;
    carried = !!from;
    const s = opts.signoff?.();
    if (from) {
      Object.assign(form, { ...from.form, items: from.form.items.slice() });
      baseline.value = { ...from.baseline };
      autoFill.value = from.autoFill;
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
      });
      baseline.value = { subject: form.subject, body: form.body };
      // a draft's own mail is kept; only a new one follows the template
      autoFill.value = !s?.email_subject;
    }
    questionsFromTemplate.value = !s && !from;
    options.reload();
  }

  /** What the dialog hands to the full page: everything typed, nothing saved. */
  function carry(): CarriedSignoff {
    return {
      form: { ...form, items: form.items.map((i) => ({ ...i })) },
      baseline: { ...baseline.value },
      autoFill: autoFill.value,
    };
  }

  // a project without a type: picked here to narrow the templates (the project is unchanged)
  const pickedType = ref("");
  const projectType = computed(
    () => data.value?.project_type || pickedType.value
  );

  // the templates for this kind of sign-off and this project's type (or any type)
  const fitting = computed<SignoffTemplate[]>(() => {
    const kind = isUat.value ? "UAT" : "Training";
    const type = projectType.value;
    return (data.value?.templates ?? []).filter(
      (t) =>
        (t.signoff_type || "Training") === kind &&
        (!t.project_type || !type || t.project_type === type)
    );
  });
  const templateOptions = computed(() => [
    ...fitting.value.map((t) => ({ label: t.template_name, value: t.name })),
    {
      label: isUat.value
        ? __("No template: the standard UAT mail")
        : __("No template: start empty"),
      value: "",
    },
  ]);
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

  function onTemplate(name: string) {
    const t = fitting.value.find((x) => x.name === name);
    // suggest the template's module, without overwriting what was typed
    if (t?.module && !form.module_title.trim()) form.module_title = t.module;
    if (questionsFromTemplate.value) loadTemplateQuestions();
  }

  /** The full page shows the template's questions to edit before saving (a UAT's come
   * from the SRS when it is saved). */
  async function loadTemplateQuestions() {
    if (!opts.withQuestions || editing.value || isUat.value) return;
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

  // ---------- the mail: filled in from the template, until it is changed by hand ----------

  const mailEdited = computed(
    () =>
      form.subject.trim() !== baseline.value.subject.trim() ||
      mailWords(form.body) !== mailWords(baseline.value.body)
  );

  // an answer for older choices must not land over the newest one
  let asked = 0;
  async function refreshMail(force = false) {
    if (!data.value?.customer) return;
    if (!force && (!autoFill.value || mailEdited.value)) return;
    const ask = ++asked;
    previewing.value = true;
    mailError.value = "";
    try {
      const mail: Mail = await call(
        "helpdesk.api.project_signoff.preview_signoff_mail",
        {
          project: opts.projectId(),
          signoff_type: isUat.value ? "UAT" : "Training",
          template: form.template || null,
          signatory_contact: form.signatory_contact || null,
          module_title: form.module_title,
          training_date: form.training_date || null,
          trainer: form.trainer || null,
          customer_address: form.customer_address || null,
          lead: opts.lead?.() || null,
        }
      );
      if (ask !== asked) return;
      form.subject = mail.subject;
      form.body = mail.body;
      baseline.value = { subject: mail.subject, body: mail.body };
      autoFill.value = true;
      // the template's own CC join who is already copied
      const cc = new Set(ccList.value.map((e) => e.toLowerCase()));
      form.cc = [...ccList.value, ...mail.cc.filter((e) => !cc.has(e))].join(
        ", "
      );
    } catch (e) {
      if (ask === asked)
        mailError.value = errorText(e, __("Couldn't fill in the mail."));
    } finally {
      if (ask === asked) previewing.value = false;
    }
  }
  const refreshSoon = useDebounceFn(() => refreshMail(), 300);
  watch(
    () => [
      form.template,
      form.signatory_contact,
      form.module_title,
      form.training_date,
      form.trainer,
      form.customer_address,
    ],
    () => data.value && refreshSoon()
  );

  function reapply() {
    confirmReapply.value = false;
    refreshMail(true);
  }

  /** What the mail still needs, in the words of the fields that fill it. */
  const unfilled = computed(() =>
    unfilledPlaceholders(`${form.subject} ${form.body}`).map(
      (name) => data.value?.placeholder_labels[name] || `{{ ${name} }}`
    )
  );

  // ---------- saving and sending ----------

  // who signs, the trainer and the module: until they are picked, the mail's gaps are theirs
  const detailsPicked = computed(
    () =>
      !!form.signatory_contact &&
      (isUat.value || (!!form.trainer && !!form.module_title.trim()))
  );

  /** Why it can't be sent yet, in words; "" when it can. */
  const sendBlocked = computed(() => {
    if (!data.value?.customer) return __("This project has no customer.");
    if (!form.signatory_contact)
      return __("Pick who signs off for the customer.");
    if (!isUat.value && !form.module_title.trim())
      return __("Name the module, e.g. Accounts.");
    if (!form.trainer)
      return isUat.value
        ? __("Pick who tests with the client.")
        : __("Pick the trainer.");
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
      !isUat.value &&
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
    const draftReady =
      (isUat.value || (!!form.module_title.trim() && !!form.trainer)) &&
      !!form.signatory_contact &&
      form.items.every((i) => i.question.trim());
    if (!draftReady) {
      errorMessage.value = isUat.value
        ? __("Pick who tests with the client and who signs.")
        : __(
            "Fill in the module, trainer and signatory, and give every question some text."
          );
      return null;
    }
    errorMessage.value = "";
    const mail = {
      email_subject: form.subject.trim(),
      email_body: mailWords(form.body) ? form.body : "",
      cc_emails: ccList.value.join(", "),
      customer_address: form.customer_address || null,
      attach_pdf: form.attach_pdf ? 1 : 0,
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
      } else if (isUat.value) {
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
    start,
    carry,
    onTemplate,
    setItems,
    reapply,
    submit,
  });
}

export type SignoffForm = ReturnType<typeof useSignoffForm>;
