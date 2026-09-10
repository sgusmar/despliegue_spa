import { useCallback, useEffect, useRef, useState } from "react";
import { getHealth, restoreOriginalModel } from "../api/client";
import type { HealthResponse } from "../types";
import { formatDateEs } from "../utils/dates";

export default function HealthWidget() {
  const [open, setOpen] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [restoreMessage, setRestoreMessage] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setHealth(await getHealth());
    } catch (err) {
      setHealth(null);
      setError(err instanceof Error ? err.message : "No se ha podido consultar el estado.");
    } finally {
      setLoading(false);
    }
  }, []);

  // Al cargar, para que el indicador diga algo real desde el principio (y de
  // paso despierte al backend, que en el plan gratuito de Render se duerme).
  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  function toggle() {
    const abriendo = !open;
    setOpen(abriendo);
    if (abriendo) {
      setConfirming(false);
      setRestoreMessage(null);
      void refresh();
    }
  }

  async function handleRestore() {
    setRestoring(true);
    setError(null);
    try {
      const res = await restoreOriginalModel();
      setRestoreMessage(res.message);
      setConfirming(false);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se ha podido restaurar el modelo.");
    } finally {
      setRestoring(false);
    }
  }

  const estado = error ? "error" : health ? "ok" : "desconocido";
  const reentrenado = health?.es_original === false;

  return (
    <div className="health-widget" ref={containerRef}>
      {open && (
        <div className="health-panel" role="dialog" aria-label="Estado del servicio">
          <div className="health-panel-head">
            <h2>Estado del servicio</h2>
            <button
              type="button"
              className="health-close"
              onClick={() => setOpen(false)}
              aria-label="Cerrar"
            >
              ×
            </button>
          </div>

          {loading && !health && <p className="health-muted">Consultando…</p>}
          {error && <div className="alert alert-error">{error}</div>}

          {health && (
            <dl className="health-list">
              <div>
                <dt>Servicio</dt>
                <dd>{health.status === "ok" ? "Operativo" : health.status}</dd>
              </div>
              <div>
                <dt>Modelo</dt>
                <dd>{health.model_loaded ? "Cargado" : "No disponible"}</dd>
              </div>
              {health.entrenado_hasta && (
                <div>
                  <dt>Entrenado hasta</dt>
                  <dd>{formatDateEs(health.entrenado_hasta)}</dd>
                </div>
              )}
              {health.version_modelo && (
                <div>
                  <dt>Versión</dt>
                  <dd>
                    <code>{health.version_modelo.slice(0, 12)}</code>
                  </dd>
                </div>
              )}
              <div>
                <dt>Origen</dt>
                <dd>{reentrenado ? "Reentrenado" : "Modelo de fábrica"}</dd>
              </div>
            </dl>
          )}

          {restoreMessage && <div className="alert alert-success">{restoreMessage}</div>}

          {reentrenado && !confirming && (
            <button
              type="button"
              className="btn btn-secondary health-action"
              onClick={() => setConfirming(true)}
            >
              Restaurar modelo original
            </button>
          )}

          {confirming && (
            <div className="health-confirm">
              <p>
                Se descartará el modelo reentrenado y los datos que se hayan subido, y
                se volverá al modelo original. Ese original nunca se sobrescribe, así
                que la operación es reversible reentrenando de nuevo.
              </p>
              <div className="health-confirm-actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleRestore}
                  disabled={restoring}
                >
                  {restoring ? <span className="spinner-inline">Restaurando</span> : "Sí, restaurar"}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setConfirming(false)}
                  disabled={restoring}
                >
                  Cancelar
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <button
        type="button"
        className="health-fab"
        onClick={toggle}
        aria-expanded={open}
        aria-label="Estado del servicio"
      >
        <span className={`health-dot health-dot-${estado}`} aria-hidden="true" />
        Estado
      </button>
    </div>
  );
}
