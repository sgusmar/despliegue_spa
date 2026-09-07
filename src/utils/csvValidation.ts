export const EXPECTED_HEADER = ["fecha", "tramo", "citas"];
export const EXAMPLE_FILE_PATH = "/ejemplo_retrain.csv";

export interface ValidationError {
  line: number;
  message: string;
}

export interface ValidationResult {
  valid: boolean;
  rowCount: number;
  errors: ValidationError[];
}

const VALID_TRAMOS = new Set(["manana", "mañana", "tarde"]);

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function normalizeHeaderCell(cell: string): string {
  return cell.trim().toLowerCase();
}

function splitCsvLine(line: string): string[] {
  return line.split(",").map((cell) => cell.trim());
}

/**
 * Valida que un texto CSV siga el esquema esperado: fecha,tramo,citas
 * (fecha YYYY-MM-DD, tramo manana/tarde, citas entero >= 0).
 */
export function validateCsv(rawText: string): ValidationResult {
  const errors: ValidationError[] = [];

  const lines = rawText
    .split(/\r\n|\n|\r/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  if (lines.length === 0) {
    return {
      valid: false,
      rowCount: 0,
      errors: [{ line: 0, message: "El contenido está vacío." }],
    };
  }

  const header = splitCsvLine(lines[0]).map(normalizeHeaderCell);
  const headerMatches =
    header.length === EXPECTED_HEADER.length &&
    header.every((cell, i) => cell === EXPECTED_HEADER[i]);

  if (!headerMatches) {
    errors.push({
      line: 1,
      message: `La cabecera debe ser exactamente "${EXPECTED_HEADER.join(
        ","
      )}" (encontrado: "${lines[0]}").`,
    });
    // Si la cabecera no coincide, no tiene sentido seguir validando filas.
    return { valid: false, rowCount: 0, errors };
  }

  const dataLines = lines.slice(1);

  dataLines.forEach((line, idx) => {
    const lineNumber = idx + 2; // +1 por índice base 0, +1 por la cabecera
    const cells = splitCsvLine(line);

    if (cells.length !== 3) {
      errors.push({
        line: lineNumber,
        message: `Se esperaban 3 columnas (fecha,tramo,citas), se encontraron ${cells.length}.`,
      });
      return;
    }

    const [fecha, tramo, citas] = cells;

    if (!DATE_RE.test(fecha) || Number.isNaN(new Date(fecha).getTime())) {
      errors.push({
        line: lineNumber,
        message: `Fecha inválida "${fecha}". Formato esperado: YYYY-MM-DD.`,
      });
    }

    if (!VALID_TRAMOS.has(tramo.toLowerCase())) {
      errors.push({
        line: lineNumber,
        message: `Tramo inválido "${tramo}". Debe ser "manana" o "tarde".`,
      });
    }

    const citasNum = Number(citas);
    if (!Number.isInteger(citasNum) || citasNum < 0) {
      errors.push({
        line: lineNumber,
        message: `Número de citas inválido "${citas}". Debe ser un entero >= 0.`,
      });
    }
  });

  return {
    valid: errors.length === 0,
    rowCount: dataLines.length,
    errors,
  };
}
