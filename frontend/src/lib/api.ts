/** Typed client for the SketchLogic FastAPI backend (`/api/v1`). */

import type { GraphDocument } from "./graph-schema";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  graph_schema_version: string;
  supported_schema_versions: string[];
  database: "ok" | "unavailable";
  inference_provider: string;
  aws_enabled: boolean;
}

export type FileKind = "png" | "jpeg" | "webp" | "xlsx";

export interface ValidationResult {
  valid: true;
  filename: string;
  kind: FileKind;
  media_type: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  sheet_names: string[];
  warnings: string[];
}

export interface UploadResponse extends ValidationResult {
  id: string;
  sha256: string;
  training_consent: boolean;
}

export interface GraphRecord {
  id: string;
  title: string;
  version: number;
  created_at: string;
  updated_at: string;
  document: GraphDocument;
}

export interface GraphListItem {
  id: string;
  title: string;
  version: number;
  updated_at: string;
}

export interface GraphVersionInfo {
  version: number;
  schema_version: string;
  created_at: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    /** Set on `graph_version_conflict`: the version the server now holds. */
    readonly currentVersion?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1${path}`, init);
  } catch {
    throw new ApiError(
      `Cannot reach the API at ${API_BASE_URL}. Is the backend running?`,
      0,
      "network_error",
    );
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) throw toApiError(res.status, body);
  return body as T;
}

function toApiError(status: number, body: unknown): ApiError {
  if (body && typeof body === "object") {
    const b = body as {
      error?: { code?: string; message?: string; current_version?: number };
      detail?: unknown;
    };
    if (b.error?.message)
      return new ApiError(
        b.error.message,
        status,
        b.error.code ?? "error",
        b.error.current_version,
      );
    if (typeof b.detail === "string") return new ApiError(b.detail, status, "http_error");
    if (Array.isArray(b.detail))
      return new ApiError("Request was invalid.", status, "invalid_request");
  }
  return new ApiError(`Request failed (HTTP ${status}).`, status, "http_error");
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/health", { signal });
}

export function validateUpload(file: File): Promise<ValidationResult> {
  const form = new FormData();
  form.append("file", file);
  return request<ValidationResult>("/uploads/validate", { method: "POST", body: form });
}

export function createUpload(file: File, trainingConsent = false): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("training_consent", String(trainingConsent));
  return request<UploadResponse>("/uploads", { method: "POST", body: form });
}

const JSON_HEADERS = { "Content-Type": "application/json" };
const graphPath = (id: string) => `/graphs/${encodeURIComponent(id)}`;

export function listGraphs(signal?: AbortSignal): Promise<GraphListItem[]> {
  return request<GraphListItem[]>("/graphs", { signal });
}

export function createGraph(document: GraphDocument): Promise<GraphRecord> {
  return request<GraphRecord>("/graphs", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(document),
  });
}

export function getGraph(id: string, signal?: AbortSignal): Promise<GraphRecord> {
  return request<GraphRecord>(graphPath(id), { signal });
}

/** Save a user edit. Rejects with `ApiError` code `graph_version_conflict` if `baseVersion` is stale. */
export function saveGraph(
  id: string,
  baseVersion: number,
  document: GraphDocument,
): Promise<GraphRecord> {
  return request<GraphRecord>(graphPath(id), {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify({ base_version: baseVersion, document }),
  });
}

export function listGraphVersions(id: string, signal?: AbortSignal): Promise<GraphVersionInfo[]> {
  return request<GraphVersionInfo[]>(`${graphPath(id)}/versions`, { signal });
}

export function getGraphVersion(
  id: string,
  version: number,
  signal?: AbortSignal,
): Promise<GraphRecord> {
  return request<GraphRecord>(`${graphPath(id)}/versions/${version}`, { signal });
}
