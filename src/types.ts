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
