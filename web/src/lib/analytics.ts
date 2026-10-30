declare global {
  const __GA_MEASUREMENT_ID__: string;

  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

const measurementId = __GA_MEASUREMENT_ID__;
if (location.origin === new URL(import.meta.env.SITE).origin) {
  const page = new URL(location.origin + location.pathname);
  const campaignKeys = [
    'utm_source',
    'utm_medium',
    'utm_campaign',
    'utm_id',
    'utm_term',
    'utm_content',
  ];
  new URLSearchParams(location.search).forEach((value, key) => {
    if (campaignKeys.includes(key)) page.searchParams.set(key, value);
  });
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () {
    window.dataLayer!.push(arguments);
  };
  window.gtag('js', new Date());
  // Keep trial amounts and history.replaceState changes out of analytics URLs.
  window.gtag('config', measurementId, {
    send_page_view: false,
    page_location: page.href,
    page_referrer: document.referrer ? new URL(document.referrer).origin : '',
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
  });
  window.gtag('event', 'page_view');
  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
  document.head.append(script);
}

export function trackCalculation(currency: string, reverse: boolean) {
  window.gtag?.('event', 'calculate', {
    foreign_currency: currency,
    conversion_direction: reverse ? 'twd-to-foreign' : 'foreign-to-twd',
  });
}
