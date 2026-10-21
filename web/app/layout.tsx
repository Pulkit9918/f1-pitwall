import type { Metadata } from "next";
import "@fontsource-variable/archivo/wdth.css";
import "./globals.css";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "f1-pitwall",
  description: "Tyre strategy, pit-stop cost and race-control periods for every Formula 1 session since 2022, measured from timing data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Nav />
        <main className="wrap">{children}</main>
        <footer className="wrap foot">
          <p>
            The figures are measured from F1 timing data and checked for internal consistency. They have not been compared
            with an outside source. The repository README lists the known gaps in the data.
          </p>
        </footer>
      </body>
    </html>
  );
}
