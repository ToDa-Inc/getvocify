import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import { isDesktopHost } from "./lib/desktop-host";
import "react-day-picker/dist/style.css";
import "./index.css";
import "./lib/theme/materials.css";

// On the web Stripe.js is on every page, as Stripe asks for its fraud signals. The desktop app keeps the page open all day,
// and Stripe's frames there were two processes of their own (about 100 MB): it loads Stripe only when a payment needs it.
if (!isDesktopHost()) void import("@stripe/stripe-js");

createRoot(document.getElementById("root")!).render(<App />);
