import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DayOccupancy } from "../types";

interface Props {
  data: DayOccupancy[];
}

const COLOR_MANANA = "#c3a583";
const COLOR_TARDE = "#6f7858";

function shortDateLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  const weekday = d.toLocaleDateString("es-ES", { weekday: "short" });
  const dayMonth = d.toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit" });
  return `${weekday} ${dayMonth}`;
}

export default function OccupancyChart({ data }: Props) {
  const chartData = data.map((d) => ({
    ...d,
    label: shortDateLabel(d.date),
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e4dccd" />
        <XAxis dataKey="label" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
        <Tooltip
          formatter={(value: number, name: string) => [
            value,
            name === "manana" ? "Mañana" : "Tarde",
          ]}
          labelFormatter={(label) => label}
        />
        <Legend
          formatter={(value) => (value === "manana" ? "Mañana" : "Tarde")}
        />
        <Bar dataKey="manana" stackId="ocupacion" fill={COLOR_MANANA} radius={[0, 0, 0, 0]} />
        <Bar dataKey="tarde" stackId="ocupacion" fill={COLOR_TARDE} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
