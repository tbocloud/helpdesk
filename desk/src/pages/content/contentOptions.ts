import { call, createResource } from "frappe-ui";
import { computed } from "vue";
import { CHANNELS, FORMATS } from "./constants";

export type ContentOptionKind = "platform" | "postType";

const DOCTYPES: Record<
  ContentOptionKind,
  { doctype: string; field: string; defaults: string[] }
> = {
  platform: {
    doctype: "HD Content Platform",
    field: "platform_name",
    defaults: CHANNELS,
  },
  postType: {
    doctype: "HD Content Post Type",
    field: "post_type_name",
    defaults: FORMATS,
  },
};

function optionList(kind: ContentOptionKind) {
  return createResource({
    url: "frappe.client.get_list",
    cache: ["content-options", kind],
    params: {
      doctype: DOCTYPES[kind].doctype,
      fields: ["name"],
      order_by: "sort_order asc, creation asc",
      limit_page_length: 0,
    },
    transform: (rows: { name: string }[]) => rows.map((r) => r.name),
    auto: true,
  });
}

// one list each for the whole app, so an option added in one dialog shows up everywhere
let lists: Record<ContentOptionKind, ReturnType<typeof optionList>> | null =
  null;

/** The platforms and post types the team can pick, including ones they added. */
export function useContentOptions() {
  lists ??= {
    platform: optionList("platform"),
    postType: optionList("postType"),
  };
  const names = (kind: ContentOptionKind) =>
    computed<string[]>(() => lists![kind].data ?? DOCTYPES[kind].defaults);

  async function addOption(kind: ContentOptionKind, name: string) {
    const { doctype, field } = DOCTYPES[kind];
    const doc = await call("frappe.client.insert", {
      doc: { doctype, [field]: name.trim() },
    });
    await lists![kind].reload();
    return doc.name as string;
  }

  return {
    platforms: names("platform"),
    postTypes: names("postType"),
    addOption,
  };
}
