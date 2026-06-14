import { redirect } from "next/navigation";

/** Legacy /returns → /resell. The seller-facing route is now /resell. */
export default function ReturnsRedirect() {
  redirect("/resell");
}
