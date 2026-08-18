import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "react-day-picker/dist/style.css";
import "./index.css";
import "./lib/theme/materials.css";

createRoot(document.getElementById("root")!).render(<App />);
