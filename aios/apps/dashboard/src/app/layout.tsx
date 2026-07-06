import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "AIOS 群健全性ダッシュボード",
  description: "マルチエージェント群の長期運用基盤 — 散逸度・適合度・Rehatchの可視化",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
