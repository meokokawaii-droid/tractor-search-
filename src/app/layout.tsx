import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "全球农机售后需求监控仪",
  description: "Real-time global agricultural machinery demand monitoring system",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-slate-50">{children}</body>
    </html>
  );
}
