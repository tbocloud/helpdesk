import type { Component } from "vue";
import LucideFile from "~icons/lucide/file";
import LucideFileCode from "~icons/lucide/file-code";
import LucideFileImage from "~icons/lucide/file-image";
import LucideFileText from "~icons/lucide/file-text";
import LucideFileType from "~icons/lucide/file-type";

export interface Person {
  user: string;
  full_name: string;
}

export interface ProjectFile {
  name: string;
  project_file: string | null;
  file_name: string;
  file_url: string;
  file_size: number;
  uploaded_by: string;
  uploaded_by_name: string;
  creation: string;
  for_users: Person[];
  is_for_me: boolean;
  can_delete: boolean;
  can_edit_for: boolean;
}

export type FileKind = "markdown" | "text" | "pdf" | "image" | "other";

/** Classify a file by its extension, for icon and in-app preview choices. */
export function fileKind(fileName: string): FileKind {
  const ext = (fileName.split(".").pop() || "").toLowerCase();
  if (ext === "md" || ext === "markdown") return "markdown";
  if (ext === "txt") return "text";
  if (ext === "pdf") return "pdf";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext))
    return "image";
  return "other";
}

/** Whether the in-app viewer can open this file, rather than just downloading it. */
export function canPreview(fileName: string) {
  return fileKind(fileName) !== "other";
}

const ICONS: Record<FileKind, Component> = {
  markdown: LucideFileCode,
  text: LucideFileText,
  pdf: LucideFileType,
  image: LucideFileImage,
  other: LucideFile,
};

/** The icon component for a file's kind. */
export function fileIcon(fileName: string): Component {
  return ICONS[fileKind(fileName)];
}

/** A human-readable file size (B/KB/MB). */
export function formatBytes(bytes?: number) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.max(Math.round(bytes / 1024), 1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Files kept in S3 open through a signed link on another host, where browsers
 * ignore the download attribute; ask the server for a "save" link instead.
 */
export function downloadHref(url: string) {
  return url.includes("helpdesk.storage.s3.download")
    ? `${url}&download=1`
    : url;
}
