import { useState } from "react";
import { predictRange } from "../api/client";
import type { RangePredictionResult } from "../types";
import { formatDateShortEs, toIsoDate, todayIso } from "../utils/dates";
import DateField from "./DateField";
import OccupancyChart from "./OccupancyChart";

function addDaysIso(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return toIsoDate(d);
}

export default function PredictRangeForm() {
  const [startDate, setStartDate] = useState(todayIso());
  const [endDate, setEndDate] = useState(addDaysIso(todayIso(), 6));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RangePredictionResult | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (startDate > endDate) {
      setError("La fecha de inicio debe ser anterior o igual a la fecha de fin.");
      return;
    }

    setLoading(true);
    setResult(null);
    try {
      const res = await predictRange({ startDate, endDate });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al predecir.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <form onSubmit={handleSubmit}>
        <div className="form-row">
          <DateField id="range-start" label="Fecha inicio" value={startDate} onChange={setStartDate} />
          <DateField id="range-end" label="Fecha fin" value={endDate} onChange={setEndDate} />
        </div>

        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? (
            <span className="spinner-inline">Prediciendo</span>
          ) : (
            "Predecir rango"
          )}
        </button>
      </form>

      {error && <div className="alert alert-error">{error}</div>}

      {result && (
        <div className="charts-grid">
          <div className="card chart-card">
            <h3>Ocupación prevista</h3>
            <p className="chart-note">
              {formatDateShortEs(startDate)} — {formatDateShortEs(endDate)}
            </p>
            <OccupancyChart data={result.current} />
          </div>

          <div className="card chart-card">
            <h3>Ocupación real (año anterior)</h3>
            <p className="chart-note">Mismo periodo, un año antes</p>
            {result.previousYear && result.previousYear.length > 0 ? (
              <OccupancyChart data={result.previousYear} />
            ) : (
              <div className="empty-chart">
                No hay datos históricos disponibles para este periodo del año
                anterior.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
