import type {
  RangePredictionRequest,
  RangePredictionResult,
  RetrainResponse,
  SinglePredictionRequest,
  SinglePredictionResult,
} from "../types";
import { mockPredictRange, mockPredictSingle, mockRetrain } from "./mock";

const API_URL = import.meta.env.VITE_API_URL as string | undefined;
const USE_MOCK = !API_URL || import.meta.env.VITE_USE_MOCK === "true";

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Error ${res.status} al llamar a ${path}`);
  }

  return res.json() as Promise<T>;
}

export async function predictSingle(
  req: SinglePredictionRequest
): Promise<SinglePredictionResult> {
  if (USE_MOCK) return mockPredictSingle(req);
  return postJson<SinglePredictionResult>("/predict/single", req);
}

export async function predictRange(
  req: RangePredictionRequest
): Promise<RangePredictionResult> {
  if (USE_MOCK) return mockPredictRange(req);
  return postJson<RangePredictionResult>("/predict/range", req);
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
    const errText = await res.text().catch(() => "");
    throw new Error(errText || `Error ${res.status} al subir el archivo`);
  }

  return res.json() as Promise<RetrainResponse>;
}

export const isMockMode = USE_MOCK;
