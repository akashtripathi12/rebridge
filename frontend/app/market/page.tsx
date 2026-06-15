import { MarketBrowser } from "@/components/market/market-browser";

/**
 * Legacy `/market` alias. The canonical customer landing is `/marketplace`
 * (role-guarded route group); this path is kept so existing links and the e2e
 * suite keep working, rendering the same shared browser.
 */
export default function MarketPage() {
  return <MarketBrowser />;
}

