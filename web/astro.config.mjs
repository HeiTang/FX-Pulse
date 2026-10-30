// @ts-check
import { defineConfig } from 'astro/config';

import tailwindcss from '@tailwindcss/vite';

export const gaMeasurementId = 'G-4CXCX1QQP7';

// https://astro.build/config
export default defineConfig({
  site: 'https://fx.purr.tw',

  build: {
    inlineStylesheets: 'always',
  },

  vite: {
    plugins: [tailwindcss()],
    define: {
      __GA_MEASUREMENT_ID__: JSON.stringify(gaMeasurementId),
    },
  },
});
