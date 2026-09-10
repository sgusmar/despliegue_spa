import type {
  HealthResponse,
  RangePredictionRequest,
  RangePredictionResult,
  RestoreResponse,
  RetrainResponse,
  SinglePredictionRequest,
  SinglePredictionResult,
} from "../types";
import {
  mockHealth,
  mockPredictRange,
  mockPredictSingle,
  mockRestore,
  mockRetrain,
} from "./mock";

// Por defecto se llama al mismo origen: en desarrollo lo resuelve el proxy de
// vite.config.ts y en Render la regla de rewrite del static site, así que no
// hay que hornear la URL del backend en el build ni habilitar CORS.
const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";
const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";

/** El backend contesta {"error": "..."}; sin esto el usuario vería el JSON crudo. */
async function readError(res: Response, fallback: string): Promise<string> {
  const text = await res.text().catch(() => "");
  if (!text) return fallback;
  try {
    const body = JSON.parse(text);
    return body.error ?? body.message ?? text;
  } catch {
    return text;
  }
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    throw new Error(await readError(res, `Error ${res.status} al llamar a ${path}`));
  }

  return res.json() as Promise<T>;
}

/** /predict/single y /predict/range son solo GET: sin cuerpo, parámetros por query string. */
async function getJson<T>(path: string, params: Record<string, string>): Promise<T> {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(`${API_URL}${path}?${query}`);

  if (!res.ok) {
    throw new Error(await readError(res, `Error ${res.status} al llamar a ${path}`));
  }

  return res.json() as Promise<T>;
}

export async function predictSingle(
  req: SinglePredictionRequest
): Promise<SinglePredictionResult> {
  if (USE_MOCK) return mockPredictSingle(req);
  return getJson<SinglePredictionResult>("/predict/single", { date: req.date, tramo: req.tramo });
}

export async function predictRange(
  req: RangePredictionRequest
): Promise<RangePredictionResult> {
  if (USE_MOCK) return mockPredictRange(req);
  return getJson<RangePredictionResult>("/predict/range", {
    startDate: req.startDate,
    endDate: req.endDate,
  });
}

export async function retrainWithText(csvText: string): Promise<RetrainResponse> {
  const rowCount = csvText.trim().split("\n").length - 1; // sin cabecera
  if (USE_MOCK) return mockRetrain(Math.max(rowCount, 0));
  return postJson<RetrainResponse>("/retrain", { csvText });
}

export async function retrainWithFile(file: File): Promise<RetrainResponse> {
  const text = await file.text();

  if (USE_MOCK) {
    const rowCount = text.trim().split("\n").length - 1;
    return mockRetrain(Math.max(rowCount, 0));
  }

  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_URL}/retrain`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    throw new Error(await readError(res, `Error ${res.status} al subir el archivo`));
  }

  return res.json() as Promise<RetrainResponse>;
}

export async function getHealth(): Promise<HealthResponse> {
  if (USE_MOCK) return mockHealth();

  const res = await fetch(`${API_URL}/health`);
  if (!res.ok) {
    throw new Error(await readError(res, `Error ${res.status} al consultar el estado`));
  }
  return res.json() as Promise<HealthResponse>;
}

/** Descarta el modelo reentrenado y los CSV subidos: vuelve al modelo de fábrica. */
export async function restoreOriginalModel(): Promise<RestoreResponse> {
  if (USE_MOCK) return mockRestore();
  return postJson<RestoreResponse>("/retrain/reset", {});
}

export const isMockMode = USE_MOCK;
