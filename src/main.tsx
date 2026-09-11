import "@fontsource-variable/inter";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AppProviders } from "./v2/AppProviders";
import RootApp from "./v2/RootApp";
import "./styles/tailwind.css";
import "./styles/v2.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <AppProviders>
      <RootApp />
    </AppProviders>
  </BrowserRouter>,
);
