export type Tramo = "manana" | "tarde";

export interface SinglePredictionRequest {
  date: string; // YYYY-MM-DD
  tramo: Tramo;
}

export interface SinglePredictionResult {
  date: string;
  tramo: Tramo;
  citasPrevistas: number;
}

export interface RangePredictionRequest {
  startDate: string; // YYYY-MM-DD
  endDate: string; // YYYY-MM-DD
}

export interface DayOccupancy {
  date: string; // YYYY-MM-DD
  manana: number;
  tarde: number;
}

export interface RangePredictionResult {
  current: DayOccupancy[];
  previousYear: DayOccupancy[] | null;
}

export interface RetrainResponse {
  status: "ok" | "error";
  rowsIngested: number;
  message: string;
}

export interface HealthResponse {
  status: string;
  model_loaded: boolean;
  entrenado_hasta?: string;
  version_modelo?: string;
  /** false cuando está activo un modelo reentrenado en lugar del de fábrica. */
  es_original?: boolean;
}

export interface RestoreResponse {
  status: "ok";
  modelRestored: boolean;
  filesRemoved: number;
  message: string;
}
