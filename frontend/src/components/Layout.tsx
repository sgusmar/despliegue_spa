import { NavLink, Outlet } from "react-router-dom";
import HealthWidget from "./HealthWidget";

export default function Layout() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <NavLink to="/" className="brand">
          <span className="brand-mark">Oasis</span>
          <span className="brand-subtitle">
            Spa Sevilla
            <br />
            Ocupación
          </span>
        </NavLink>
        <nav className="main-nav">
          <NavLink to="/" end>
            Inicio
          </NavLink>
          <NavLink to="/predict">Predicción</NavLink>
          <NavLink to="/retrain">Reentrenar</NavLink>
          {/* /api/docs, no una ruta de React Router: es la documentación
              interactiva (Swagger UI) que sirve el backend, una página
              aparte. <a> normal, no NavLink, para que sea una navegación de
              verdad y no la intente resolver el router del front. */}
          <a href="/api/docs" target="_blank" rel="noopener noreferrer">
            API Docs
          </a>
        </nav>
      </header>

      <main className="app-main">
        <Outlet />
      </main>

      <footer className="app-footer">
        Oasis Spa Sevilla · Modelo interno de predicción de ocupación
      </footer>

      <HealthWidget />
    </div>
  );
}
