import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type S = components["schemas"];

declare global {
  interface Window {
    __BASE_PATH__?: string;
  }
}

/** URL prefix the app is served under ("/" normally, "/api/hassio_ingress/<token>/" under HA ingress). */
export const BASE_PATH: string = window.__BASE_PATH__ ?? "/";

export const api = createClient<paths>({
  baseUrl: BASE_PATH.replace(/\/$/, ""),
  credentials: "same-origin",
});

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

export function errorMessage(error: unknown, fallback = "Request failed"): string {
  if (!error || typeof error !== "object") return fallback;
  const detail = (error as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: (string | number)[]; msg?: string }) => {
        const field = d.loc?.filter((l) => l !== "body").join(".");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  if (error instanceof Error) return error.message;
  return fallback;
}

/** Await an openapi-fetch call and return its data, throwing ApiError on failure. */
export async function unwrap<T>(promise: Promise<FetchResult<T>>): Promise<T> {
  const { data, error, response } = await promise;
  if (!response.ok || error !== undefined) {
    throw new ApiError(errorMessage(error, `${response.status} ${response.statusText}`), response.status);
  }
  return data as T;
}

export function mediaUrl(id: number, variant: "thumb" | "file" = "thumb"): string {
  return `${BASE_PATH}api/v1/media/${id}/${variant}`;
}

export interface UploadOptions {
  caption?: string;
  takenAt?: string;
  plantId?: number;
  instanceId?: number;
  eventId?: number;
  logPhotoEvent?: boolean;
}

export async function uploadMedia(file: File, opts: UploadOptions = {}): Promise<S["MediaRead"]> {
  const form = new FormData();
  form.append("file", file);
  if (opts.caption) form.append("caption", opts.caption);
  if (opts.takenAt) form.append("taken_at", opts.takenAt);
  if (opts.plantId) form.append("plant_id", String(opts.plantId));
  if (opts.instanceId) form.append("instance_id", String(opts.instanceId));
  if (opts.eventId) form.append("event_id", String(opts.eventId));
  if (opts.logPhotoEvent) form.append("log_photo_event", "true");
  const response = await fetch(`${BASE_PATH}api/v1/media`, { method: "POST", body: form, credentials: "same-origin" });
  const body = await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiError(errorMessage(body, "Upload failed"), response.status);
  return body;
}
