import type {
  DayOccupancy,
  RangePredictionRequest,
  RangePredictionResult,
  RetrainResponse,
  SinglePredictionRequest,
  SinglePredictionResult,
  Tramo,
} from "../types";
import { toIsoDate } from "../utils/dates";

// Fecha a partir de la cual el mock "tiene" datos históricos reales.
// Antes de esta fecha, las consultas de año anterior devuelven null (sin datos).
const HISTORICAL_DATA_START = new Date("2024-01-01T00:00:00");

function hashString(input: string): number {
  let hash = 0;
  for (let i = 0; i < input.length; i++) {
    hash = (hash << 5) - hash + input.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function pseudoRandom(seed: string): number {
  const hash = hashString(seed);
  return (hash % 1000) / 1000;
}

function citasParaTramo(date: string, tramo: Tramo): number {
  const d = new Date(`${date}T00:00:00`);
  const dayOfWeek = d.getDay(); // 0 domingo ... 6 sábado
  const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;

  const base = tramo === "manana" ? 14 : 18;
  const weekendBonus = isWeekend ? 8 : 0;
  const noise = Math.round(pseudoRandom(`${date}-${tramo}`) * 10) - 5;

  return Math.max(0, base + weekendBonus + noise);
}

function addYears(date: Date, years: number): Date {
  const copy = new Date(date);
  copy.setFullYear(copy.getFullYear() + years);
  return copy;
}

function buildSeries(startDate: string, endDate: string): DayOccupancy[] {
  const series: DayOccupancy[] = [];
  const start = new Date(`${startDate}T00:00:00`);
  const end = new Date(`${endDate}T00:00:00`);

  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const dateStr = toIsoDate(d);
    series.push({
      date: dateStr,
      manana: citasParaTramo(dateStr, "manana"),
      tarde: citasParaTramo(dateStr, "tarde"),
    });
  }

  return series;
}

function simulateLatency<T>(value: T, ms = 500): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

export async function mockPredictSingle(
  req: SinglePredictionRequest
): Promise<SinglePredictionResult> {
  const result: SinglePredictionResult = {
    date: req.date,
    tramo: req.tramo,
    citasPrevistas: citasParaTramo(req.date, req.tramo),
  };
  return simulateLatency(result);
}

export async function mockPredictRange(
  req: RangePredictionRequest
): Promise<RangePredictionResult> {
  const current = buildSeries(req.startDate, req.endDate);

  const prevStart = addYears(new Date(`${req.startDate}T00:00:00`), -1);
  const prevEnd = addYears(new Date(`${req.endDate}T00:00:00`), -1);

  const hasHistoricalData = prevStart >= HISTORICAL_DATA_START;

  const previousYear = hasHistoricalData
    ? buildSeries(toIsoDate(prevStart), toIsoDate(prevEnd))
    : null;

  return simulateLatency({ current, previousYear });
}

export async function mockRetrain(rowCount: number): Promise<RetrainResponse> {
  return simulateLatency({
    status: "ok",
    rowsIngested: rowCount,
    message: `Se han recibido ${rowCount} filas correctamente. El modelo se reentrenará con estos datos.`,
  });
}
