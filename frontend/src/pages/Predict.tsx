import { useState } from "react";
import PredictRangeForm from "../components/PredictRangeForm";
import PredictSingleForm from "../components/PredictSingleForm";

type Mode = "single" | "range";

export default function Predict() {
  const [mode, setMode] = useState<Mode>("single");

  return (
    <div>
      <h1 className="page-title">Predicción de ocupación</h1>
      <p className="page-subtitle">
        Consulta la ocupación prevista para un día y tramo concretos, o
        analiza un rango de fechas comparándolo con el año anterior.
      </p>

      <div className="mode-toggle" role="tablist" aria-label="Modo de predicción">
        <button
          type="button"
          className={mode === "single" ? "active" : ""}
          onClick={() => setMode("single")}
          role="tab"
          aria-selected={mode === "single"}
        >
          Fecha única
        </button>
        <button
          type="button"
          className={mode === "range" ? "active" : ""}
          onClick={() => setMode("range")}
          role="tab"
          aria-selected={mode === "range"}
        >
          Rango de fechas
        </button>
      </div>

      <div className="card">
        {mode === "single" ? <PredictSingleForm /> : <PredictRangeForm />}
      </div>
    </div>
  );
}
