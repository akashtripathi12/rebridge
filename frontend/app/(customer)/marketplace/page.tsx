import { MarketBrowser } from "@/components/market/market-browser";

/**
 * Customer landing — the Second-Chance marketplace. This is where a customer is
 * sent after login and where operators are redirected away from (by the group
 * guard). Renders the shared browser used by the legacy `/market` alias.
 */
export default function MarketplacePage() {
  return <MarketBrowser />;
}
