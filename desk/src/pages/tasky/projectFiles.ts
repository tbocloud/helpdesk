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

export type ItemStatus = "Active" | "Superseded";
export type ItemKind = "file" | "folder";

/** Active / Superseded, shared by files and folders. */
interface StatusFields {
  status: ItemStatus;
  /** What replaces it, when someone said so. */
  superseded_by: { name: string; label: string; folder?: string | null } | null;
  status_note: string;
  status_changed_by_name: string;
  status_changed_on: string | null;
  comment_count: number;
}

/** A file or folder that status changes and comments are about. */
export interface ItemRef {
  kind: ItemKind;
  /** The File's name for a file, the folder's name for a folder. */
  name: string;
  label: string;
}

export interface ItemComment {
  name: string;
  text: string;
  author: string;
  author_name: string;
  creation: string;
  edited: boolean;
  can_edit: boolean;
  can_delete: boolean;
}

export interface ProjectFile extends StatusFields {
  name: string;
  project_file: string | null;
  file_name: string;
  file_url: string;
  file_size: number;
  uploaded_by: string;
  uploaded_by_name: string;
  creation: string;
  /** The folder it is in; null at the top level. */
  folder: string | null;
  /** Top level first; empty at the top level. */
  folder_path: FolderCrumb[];
  for_users: Person[];
  is_for_me: boolean;
  /** In a folder (or below one) that is for the current user. */
  shared_via_folder: boolean;
  /** Its folder or one above it is superseded (display only). */
  in_superseded_folder: boolean;
  can_delete: boolean;
  can_edit_for: boolean;
}

export interface FolderCrumb {
  name: string;
  folder_name: string;
}

export interface ProjectFolder extends StatusFields {
  name: string;
  folder_name: string;
  /** null at the top level. */
  parent_folder: string | null;
  /** 1 at the top level. */
  depth: number;
  /** Levels from this folder down to its deepest subfolder, itself included. */
  height: number;
  description: string;
  created_by: string;
  created_by_name: string;
  creation: string;
  file_count: number;
  folder_count: number;
  for_users: Person[];
  is_for_me: boolean;
  /** A folder above it is for the current user. */
  for_me_via_parent: boolean;
  /** A folder above it is superseded (display only). */
  superseded_via_parent: boolean;
  /** Rename, move, change who it's for, delete. */
  can_change: boolean;
}

/** The open folder, with the way down to it. */
export interface OpenFolder extends ProjectFolder {
  path: FolderCrumb[];
}

/** What "Move to folder" moves: a file, or a folder with everything in it. */
export interface MoveItem {
  kind: "file" | "folder";
  name: string;
  label: string;
  /** Where it is now; null at the top level. */
  current: string | null;
  /** For a folder: its levels, itself included. */
  height?: number;
}

/** Why an item shows as superseded: its own status, a folder above it, or not at all. */
export function supersededVia(
  item: ProjectFile | ProjectFolder
): "own" | "folder" | null {
  if (item.status === "Superseded") return "own";
  const inherited =
    "in_superseded_folder" in item
      ? item.in_superseded_folder
      : item.superseded_via_parent;
  return inherited ? "folder" : null;
}

// "@Full Name" of anyone on the team, longest names first so "@Ann Lee" isn't read as "@Ann"
function mentionPattern(team: Person[]) {
  const names = [...new Set(team.map((p) => p.full_name).filter(Boolean))]
    .sort((a, b) => b.length - a.length)
    .map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return names.length
    ? new RegExp(`@(${names.join("|")})(?![\\p{L}\\p{N}])`, "gu")
    : null;
}

/** The people on the team @mentioned in a comment. */
export function mentionedUsers(text: string, team: Person[]): string[] {
  const pattern = mentionPattern(team);
  if (!pattern) return [];
  const names = new Set([...text.matchAll(pattern)].map((m) => m[1]));
  return team.filter((p) => names.has(p.full_name)).map((p) => p.user);
}

/** A comment split into plain text and @mentions, for showing mentions apart. */
export function mentionSegments(
  text: string,
  team: Person[]
): { text: string; mention: boolean }[] {
  const pattern = mentionPattern(team);
  const parts: { text: string; mention: boolean }[] = [];
  let last = 0;
  for (const m of pattern ? text.matchAll(pattern) : []) {
    const at = m.index ?? 0;
    if (at > last) parts.push({ text: text.slice(last, at), mention: false });
    parts.push({ text: m[0], mention: true });
    last = at + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last), mention: false });
  return parts;
}

/** The folder and everything below it, from the flat list. */
export function subtree(folders: ProjectFolder[], name: string): Set<string> {
  const found = new Set([name]);
  // the list comes parents first, so one pass finds every descendant
  for (const f of folders)
    if (f.parent_folder && found.has(f.parent_folder)) found.add(f.name);
  return found;
}

/** A file to upload and the folder path it came from ("" when loose). */
export interface UploadItem {
  file: File;
  dir: string;
}

const SYSTEM_FILES = new Set(["thumbs.db", "desktop.ini"]);

// .DS_Store, .git/…, Thumbs.db: things people never mean to share
function isHidden(path: string) {
  return path
    .split("/")
    .some(
      (part) => part.startsWith(".") || SYSTEM_FILES.has(part.toLowerCase())
    );
}

function uploadItem(file: File, relativePath: string): UploadItem | null {
  if (isHidden(relativePath)) return null;
  const parts = relativePath.split("/");
  parts.pop();
  return { file, dir: parts.join("/") };
}

/** Files from an <input>, with their folders when a whole folder was picked. */
export function fromFileList(files: FileList | File[]): UploadItem[] {
  return [...files]
    .map((f) => uploadItem(f, f.webkitRelativePath || f.name))
    .filter((i): i is UploadItem => !!i);
}

function readEntries(reader: FileSystemDirectoryReader) {
  return new Promise<FileSystemEntry[]>((resolve, reject) =>
    reader.readEntries(resolve, reject)
  );
}

async function walk(entry: FileSystemEntry, out: UploadItem[]) {
  const path = entry.fullPath.replace(/^\//, "");
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) =>
      (entry as FileSystemFileEntry).file(resolve, reject)
    );
    const found = uploadItem(file, path);
    if (found) out.push(found);
    return;
  }
  if (isHidden(path)) return;
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  // readEntries hands over a batch at a time, and an empty one at the end
  for (let batch = await readEntries(reader); batch.length; ) {
    for (const child of batch) await walk(child, out);
    batch = await readEntries(reader);
  }
}

/** Dropped files and whole folders, keeping each file's folder path. */
export async function fromDataTransfer(
  transfer: DataTransfer
): Promise<UploadItem[]> {
  // take the entries before the first await; the browser empties them after
  const entries = [...transfer.items]
    .filter((i) => i.kind === "file")
    .map((i) => i.webkitGetAsEntry?.() ?? null);
  if (!entries.length || entries.some((e) => !e))
    return fromFileList(transfer.files);
  const out: UploadItem[] = [];
  for (const entry of entries) await walk(entry!, out);
  return out;
}

export type FileKind = "markdown" | "text" | "pdf" | "image" | "other";

export function fileKind(fileName: string): FileKind {
  const ext = (fileName.split(".").pop() || "").toLowerCase();
  if (ext === "md" || ext === "markdown") return "markdown";
  if (ext === "txt") return "text";
  if (ext === "pdf") return "pdf";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext))
    return "image";
  return "other";
}

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

export function fileIcon(fileName: string): Component {
  return ICONS[fileKind(fileName)];
}

export function formatBytes(bytes?: number) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.max(Math.round(bytes / 1024), 1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// Files kept in S3 open through a signed link on another host, where browsers
// ignore the download attribute; ask the server for a "save" link instead
export function downloadHref(url: string) {
  return url.includes("helpdesk.storage.s3.download")
    ? `${url}&download=1`
    : url;
}
