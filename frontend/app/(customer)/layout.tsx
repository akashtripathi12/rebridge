import { RoleRouteGuard } from "@/components/chrome/role-route-guard";

/**
 * Customer route group `(customer)` — buyer-facing surfaces (marketplace +
 * matches). The group name is in parentheses so it adds no URL segment: pages
 * live at `/marketplace`, not `/customer/marketplace`. Operators are redirected
 * to their review console; signed-out visitors to /login.
 */
export default function CustomerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <RoleRouteGuard allow="customer">{children}</RoleRouteGuard>;
}
