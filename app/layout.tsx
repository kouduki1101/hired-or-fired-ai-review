import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hired or Fired | AI Code Review Challenge",
  description:
    "AIが書いたコードをレビューし、要件とのズレを見抜く5分のコードレビュー面接ゲーム。"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <div className="app-shell">
          <header className="top-nav">
            <Link className="brand" href="/">
              <span className="brand-mark">HF</span>
              <span>
                Hired or Fired
                <br />
                <span className="muted" style={{ fontSize: "0.82rem" }}>
                  AI Code Review Challenge
                </span>
              </span>
            </Link>
            <nav className="nav-links" aria-label="Primary navigation">
              <Link className="nav-link" href="/learn/python">
                Python Review Guide
              </Link>
              <Link className="nav-link" href="/problems">
                Interview Challenges
              </Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
