import type { SinglePredictionResult } from "../types";
import { formatDateEs, tramoLabel } from "../utils/dates";

interface Props {
  result: SinglePredictionResult;
}

export default function SinglePredictionTable({ result }: Props) {
  return (
    <table className="result-table">
      <tbody>
        <tr>
          <th scope="row">Fecha</th>
          <td>{formatDateEs(result.date)}</td>
        </tr>
        <tr>
          <th scope="row">Tramo</th>
          <td>{tramoLabel(result.tramo)}</td>
        </tr>
        <tr>
          <th scope="row">Citas previstas</th>
          <td>
            <strong>{result.citasPrevistas}</strong>
          </td>
        </tr>
      </tbody>
    </table>
  );
}
