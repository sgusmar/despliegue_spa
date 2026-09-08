/**
 * Formatea una fecha a YYYY-MM-DD usando los componentes locales.
 * A propósito NO usa toISOString(), que convierte a UTC y desplaza
 * el día en zonas horarias adelantadas a UTC (p.ej. España).
 */
export function toIsoDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function todayIso(): string {
  return toIsoDate(new Date());
}

export function formatDateEs(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("es-ES", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatDateShortEs(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

export function tramoLabel(tramo: string): string {
  return tramo === "manana" ? "Mañana" : "Tarde";
}
