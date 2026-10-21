"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/seasons", label: "Seasons" },
  { href: "/sessions", label: "Sessions" },
  { href: "/circuits", label: "Circuits" },
];

export function Nav() {
  const path = usePathname();
  return (
    <header className="nav">
      <div className="wrap nav-inner">
        <Link href="/" className="wordmark" aria-label="f1-pitwall home">pitwall</Link>
        <nav aria-label="Main">
          <ul>
            {LINKS.map((l) => (
              <li key={l.href}>
                <Link href={l.href} aria-current={path.startsWith(l.href) ? "page" : undefined}>{l.label}</Link>
              </li>
            ))}
            <li>
              <a href="https://github.com/Pulkit9918/f1-pitwall" rel="noreferrer">Source</a>
            </li>
          </ul>
        </nav>
      </div>
    </header>
  );
}
