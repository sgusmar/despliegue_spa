import { useState } from "react";
import { predictSingle } from "../api/client";
import type { SinglePredictionResult, Tramo } from "../types";
import { todayIso } from "../utils/dates";
import DateField from "./DateField";
import SinglePredictionTable from "./SinglePredictionTable";

export default function PredictSingleForm() {
  const [date, setDate] = useState(todayIso());
  const [tramo, setTramo] = useState<Tramo>("manana");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SinglePredictionResult | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await predictSingle({ date, tramo });
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
          <DateField id="single-date" label="Fecha" value={date} onChange={setDate} />

          <div className="field">
            <label htmlFor="single-tramo">Tramo</label>
            <select
              id="single-tramo"
              value={tramo}
              onChange={(e) => setTramo(e.target.value as Tramo)}
            >
              <option value="manana">Mañana</option>
              <option value="tarde">Tarde</option>
            </select>
          </div>
        </div>

        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? (
            <span className="spinner-inline">Prediciendo</span>
          ) : (
            "Predecir"
          )}
        </button>
      </form>

      {error && <div className="alert alert-error">{error}</div>}

      {result && (
        <>
          <h3>Resultado</h3>
          <SinglePredictionTable result={result} />
        </>
      )}
    </div>
  );
}
