import { __ } from "@/translation";

/** Where a lead is, as TBO Smart's get_lead returns it (hub-leads-api.md §2.11). */
export interface LeadPlace {
  google_profile_url: string | null;
  maps_url: string | null;
  latitude: number | null;
  longitude: number | null;
  location_note: string | null;
}

/** One photo of a lead as get_lead_photos lists it. */
export interface LeadPhoto {
  name: string;
  file_name: string;
  file_size?: number;
  caption: string | null;
  uploaded_by: string;
  uploaded_by_name?: string;
  uploaded_on: string;
}

/** The ERP site holds at most this many photos per lead. */
export const LEAD_PHOTO_LIMIT = 20;
/** Photos are scaled down in the browser before they are sent (a phone's 12 MP is far more
 * than a visit needs, and a JPEG of this size keeps a mobile upload quick). */
const PHOTO_MAX_SIDE = 2000;
const PHOTO_QUALITY = 0.85;
const ERP_ACCEPTS = ["image/jpeg", "image/png", "image/webp"];

export const hasPlace = (place?: LeadPlace | null) =>
  !!place &&
  !!(
    place.google_profile_url ||
    place.maps_url ||
    place.location_note ||
    hasPin(place)
  );

export const hasPin = (
  place?: Pick<LeadPlace, "latitude" | "longitude"> | null
) => place?.latitude != null && place?.longitude != null;

const pin = (place: LeadPlace) => `${place.latitude},${place.longitude}`;

/** Google Maps directions to the pin: opens the Maps app on a phone. Without a pin there is
 * nothing exact to route to, so no link (the map link opens as it is). */
export function directionsUrl(place: LeadPlace): string | null {
  if (!hasPin(place)) return null;
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(
    pin(place)
  )}`;
}

/** Google's own embed of a pin; it needs no API key. */
export function embedUrl(place: LeadPlace): string | null {
  if (!hasPin(place)) return null;
  return `https://www.google.com/maps?q=${encodeURIComponent(
    pin(place)
  )}&z=16&output=embed`;
}

/** The latitude and longitude a long Google Maps link carries (`@lat,lng`, `!3d..!4d..` or
 * `q=lat,lng`); null for a short link, which only Google can resolve. */
export function coordsFromMapsUrl(
  url: string
): { latitude: number; longitude: number } | null {
  const text = decodeURIComponent(url || "");
  const found =
    text.match(/!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)/) ||
    text.match(/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/) ||
    text.match(
      /[?&](?:q|ll|destination)=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)/
    );
  if (!found) return null;
  const latitude = Number(found[1]);
  const longitude = Number(found[2]);
  if (Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return null;
  return { latitude, longitude };
}

/** A photo, loaded through the hub (the ERP site's files are private). */
export function photoUrl(lead: string, file: string, thumb = false) {
  const params = new URLSearchParams({ lead, file });
  if (thumb) params.set("thumb", "1");
  return `/api/method/helpdesk.api.leads.lead_photo?${params}`;
}

/** Why the browser couldn't give the position, in words for the person. */
export function geolocationMessage(error: unknown): string {
  const code = (error as GeolocationPositionError | undefined)?.code;
  if (code === 1)
    return __(
      "Location is turned off for this site. Allow it in your browser's settings, or paste a map link."
    );
  if (code === 2)
    return __(
      "Couldn't find your position. Move to open sky or check that location is on, or paste a map link."
    );
  if (code === 3) return __("Finding your position took too long. Try again.");
  return __("This device can't share its location. Paste a map link instead.");
}

/** The device's position (one fix, as exact as it can give). */
export function currentPosition(): Promise<{
  latitude: number;
  longitude: number;
}> {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator) || !window.isSecureContext) {
      reject(new Error("unsupported"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) =>
        resolve({
          latitude: Number(p.coords.latitude.toFixed(6)),
          longitude: Number(p.coords.longitude.toFixed(6)),
        }),
      reject,
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }
    );
  });
}

function readBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

/** A chosen picture as a base64 JPEG scaled to at most 2000 px, upright and without the
 * location its EXIF carries. A picture the browser can't decode (HEIC outside Safari) is
 * sent as it is when the ERP site accepts its type, else refused with a plain reason. */
export async function preparePhoto(
  file: File
): Promise<{ filename: string; content: string }> {
  const stem = file.name.replace(/\.[^.]+$/, "") || "photo";
  try {
    const bitmap = await createImageBitmap(file, {
      imageOrientation: "from-image",
    });
    const scale = Math.min(
      1,
      PHOTO_MAX_SIDE / Math.max(bitmap.width, bitmap.height)
    );
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("no canvas");
    context.fillStyle = "#fff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((done) =>
      canvas.toBlob(done, "image/jpeg", PHOTO_QUALITY)
    );
    if (!blob) throw new Error("no jpeg");
    return { filename: `${stem}.jpg`, content: await readBase64(blob) };
  } catch {
    if (ERP_ACCEPTS.includes(file.type) && file.size <= 10 * 1024 * 1024)
      return { filename: file.name, content: await readBase64(file) };
    throw new Error(
      __(
        "{0} can't be read as a photo. Take it as JPEG or choose another.",
        file.name
      )
    );
  }
}
