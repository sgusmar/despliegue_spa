import { useRef, useState } from "react";
import { retrainWithFile, retrainWithText } from "../api/client";
import type { RetrainResponse } from "../types";
import {
  EXAMPLE_FILE_PATH,
  EXPECTED_HEADER,
  validateCsv,
  type ValidationResult,
} from "../utils/csvValidation";

type InputMode = "text" | "file";

const PLACEHOLDER = `${EXPECTED_HEADER.join(",")}\n2026-07-01,manana,4\n2026-07-01,tarde,7`;

export default function Retrain() {
  const [mode, setMode] = useState<InputMode>("file");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileText, setFileText] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [response, setResponse] = useState<RetrainResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeContent = mode === "text" ? text : fileText;
  const validation: ValidationResult | null =
    activeContent.trim().length > 0 ? validateCsv(activeContent) : null;

  async function handleFileSelected(selected: File | null) {
    setResponse(null);
    setSubmitError(null);
    setFile(selected);
    if (!selected) {
      setFileText("");
      return;
    }
    const content = await selected.text();
    setFileText(content);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files?.[0] ?? null;
    if (dropped) void handleFileSelected(dropped);
  }

  async function handleSubmit() {
    if (!validation?.valid) return;
    setSubmitting(true);
    setSubmitError(null);
    setResponse(null);
    try {
      const res =
        mode === "text" ? await retrainWithText(text) : file ? await retrainWithFile(file) : null;
      if (res) setResponse(res);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Error al enviar los datos."
      );
    } finally {
      setSubmitting(false);
    }
  }

  function resetOutcome() {
    setResponse(null);
    setSubmitError(null);
  }

  return (
    <div>
      <h1 className="page-title">Reentrenar el modelo</h1>
      <p className="page-subtitle">
        Aporta nuevos datos reales de ocupación para reentrenar el modelo.
        Puedes pegar el contenido como texto o subir un archivo, siempre que
        siga el mismo formato que el ejemplo.
      </p>

      <a href={EXAMPLE_FILE_PATH} download className="example-link">
        📄 Descargar archivo de ejemplo (ejemplo_retrain.csv)
      </a>

      <div className="card">
        <p style={{ marginTop: 0, color: "var(--color-text-muted)", fontSize: "0.9rem" }}>
          Formato esperado: cabecera <code>{EXPECTED_HEADER.join(",")}</code>{" "}
          seguida de una fila por cada fecha y tramo, con el número de citas
          reales de ese tramo.
        </p>

        <div className="retrain-input-toggle">
          <button
            type="button"
            className={`btn ${mode === "file" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => {
              setMode("file");
              resetOutcome();
            }}
          >
            Subir archivo
          </button>
          <button
            type="button"
            className={`btn ${mode === "text" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => {
              setMode("text");
              resetOutcome();
            }}
          >
            Pegar texto
          </button>
        </div>

        {mode === "file" ? (
          <div
            className={`dropzone ${dragOver ? "dragover" : ""}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            role="button"
            tabIndex={0}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.txt,text/csv,text/plain"
              onChange={(e) => void handleFileSelected(e.target.files?.[0] ?? null)}
            />
            <p style={{ margin: 0 }}>
              Arrastra aquí tu archivo .csv o haz clic para seleccionarlo
            </p>
            {file && <p className="file-name">Archivo seleccionado: {file.name}</p>}
          </div>
        ) : (
          <textarea
            className="csv-textarea"
            placeholder={PLACEHOLDER}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              resetOutcome();
            }}
          />
        )}

        {validation && !validation.valid && (
          <div className="alert alert-error">
            <strong>El formato no coincide con el ejemplo:</strong>
            <ul>
              {validation.errors.slice(0, 8).map((err, i) => (
                <li key={i}>
                  {err.line > 0 ? `Línea ${err.line}: ` : ""}
                  {err.message}
                </li>
              ))}
            </ul>
            {validation.errors.length > 8 && (
              <p>…y {validation.errors.length - 8} error(es) más.</p>
            )}
          </div>
        )}

        {validation?.valid && (
          <div className="alert alert-success">
            Formato válido: {validation.rowCount} fila(s) lista(s) para enviar.
          </div>
        )}

        {submitError && <div className="alert alert-error">{submitError}</div>}

        {/* El backend responde 200 con status "error" cuando el modelo candidato
            no supera la validación: los datos han llegado bien, pero el modelo
            NO se ha reemplazado, y eso no puede salir en verde. */}
        {response && (
          <div className={`alert ${response.status === "ok" ? "alert-success" : "alert-error"}`}>
            {response.message}
          </div>
        )}

        <button
          type="button"
          className="btn btn-primary"
          disabled={!validation?.valid || submitting}
          onClick={handleSubmit}
          style={{ marginTop: "1.25rem" }}
        >
          {submitting ? (
            <span className="spinner-inline">Enviando</span>
          ) : (
            "Enviar datos para reentrenar"
          )}
        </button>
      </div>
    </div>
  );
}
