import { Link } from "react-router-dom";

export default function Home() {
  return (
    <div>
      <section className="hero">
        <h1>Predicción de ocupación del spa</h1>
        <p>
          Esta aplicación muestra en producción nuestro modelo de Machine
          Learning entrenado con el histórico de citas del spa. A partir de
          una fecha y un tramo (mañana o tarde), el modelo estima el número de
          citas esperadas, lo que ayuda a anticipar necesidades de personal y
          recursos.
        </p>
      </section>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>¿Cómo funciona?</h2>
        <ol className="how-it-works">
          <li>
            <strong>Predicción puntual:</strong> elige una fecha y un tramo
            (mañana/tarde) y obtén la ocupación prevista en forma de tabla.
          </li>
          <li>
            <strong>Predicción por rango:</strong> elige un rango de fechas y
            visualiza la ocupación prevista de ambos tramos en un gráfico de
            barras apiladas, junto a la ocupación real del mismo periodo del
            año anterior (cuando existan datos históricos).
          </li>
          <li>
            <strong>Reentrenar el modelo:</strong> aporta nuevos datos de
            ocupación real (pegando texto o subiendo un archivo) para que el
            modelo pueda reentrenarse con información más reciente.
          </li>
        </ol>

        <div className="nav-cards">
          <Link to="/predict" className="nav-card">
            <span className="nav-card-icon" aria-hidden="true">
              📊
            </span>
            <h2>Ir a Predicción</h2>
            <p>
              Consulta la ocupación prevista para un día concreto o para un
              rango de fechas, comparándola con el año anterior.
            </p>
          </Link>

          <Link to="/retrain" className="nav-card">
            <span className="nav-card-icon" aria-hidden="true">
              🔁
            </span>
            <h2>Ir a Reentrenar</h2>
            <p>
              Añade nuevos datos de ocupación real para reentrenar el modelo,
              pegando texto o subiendo un archivo con el formato esperado.
            </p>
          </Link>
        </div>
      </section>
    </div>
  );
}
