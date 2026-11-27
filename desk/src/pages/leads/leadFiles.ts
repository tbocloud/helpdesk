/** A lead's files on the ERP site: what may be attached (hub-leads-api.md §2.34; the ERP
 *  site checks it again) and the link that opens one. */

export const LEAD_FILE_LIMIT = 50;
const MAX_BYTES = 10 * 1024 * 1024;
const EXTENSIONS = [
  ".pdf",
  ".doc",
  ".docx",
  ".xls",
  ".xlsx",
  ".ppt",
  ".pptx",
  ".odt",
  ".ods",
  ".csv",
  ".txt",
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
  ".zip",
];
export const LEAD_FILE_ACCEPT = EXTENSIONS.join(",");

const extension = (name: string) =>
  (name.match(/\.[^.]+$/)?.[0] || "").toLowerCase();

/** Whether the ERP site takes this file on a lead: its type and size. */
export function attachable(file: File) {
  return EXTENSIONS.includes(extension(file.name)) && file.size <= MAX_BYTES;
}

/** The file, streamed from the ERP site to people who may read the lead. */
export function leadFileUrl(lead: string, file: string, filename: string) {
  const params = new URLSearchParams({ lead, file, filename });
  return `/api/method/helpdesk.api.leads.lead_file?${params}`;
}
