import type { Preview } from "@storybook/react";
import { mswLoader } from "msw-storybook-addon/csf3";
import "../src/styles/tailwind.css";
import "../src/styles/tokens.css";
import "../src/styles/app.css";
import "../src/styles/v2.css";

const preview: Preview = {
  parameters: {
    a11y: { test: "error" },
    controls: { matchers: { color: /(background|color)$/i, date: /Date$/i } },
  },
  loaders: [mswLoader()],
};

export default preview;
