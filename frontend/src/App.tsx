import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Home from "./pages/Home";
import Predict from "./pages/Predict";
import Retrain from "./pages/Retrain";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="predict" element={<Predict />} />
        <Route path="retrain" element={<Retrain />} />
      </Route>
    </Routes>
  );
}
