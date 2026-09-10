import DatePicker, { registerLocale } from "react-datepicker";
import { es } from "date-fns/locale/es";
import { toIsoDate } from "../utils/dates";

registerLocale("es", es);

interface Props {
  id: string;
  label: string;
  value: string; // ISO yyyy-MM-dd
  onChange: (iso: string) => void;
}

function parseIso(iso: string): Date | null {
  if (!iso) return null;
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export default function DateField({ id, label, value, onChange }: Props) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <DatePicker
        id={id}
        selected={parseIso(value)}
        onChange={(date: Date | null) => date && onChange(toIsoDate(date))}
        dateFormat="dd/MM/yyyy"
        locale="es"
        className="date-input"
        wrapperClassName="date-input-wrapper"
        required
      />
    </div>
  );
}
