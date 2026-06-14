import type { Metadata } from "next";
import { Archivo, Manrope, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { SiteNav } from "@/components/chrome/site-nav";
import { SiteFooter } from "@/components/chrome/site-footer";

const archivo = Archivo({
  subsets: ["latin"],
  weight: ["600", "700", "800", "900"],
  variable: "--font-archivo",
  display: "swap",
});
const manrope = Manrope({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-manrope",
  display: "swap",
});
const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ReBridge — every product finds its next owner",
  description:
    "AI-graded returns with a verifiable Product Health Card, routed to resale, a neighbour, refurb, or donation in under two seconds.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${archivo.variable} ${manrope.variable} ${jetbrains.variable}`}
    >
      <body>
        <Providers>
          <SiteNav />
          <div className="min-h-[calc(100vh-3.5rem)]">{children}</div>
          <SiteFooter />
        </Providers>
      </body>
    </html>
  );
}
