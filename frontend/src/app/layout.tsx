import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BTC QUANTUM INTELLIGENCE — Real-Time Bitcoin Trading Research & Signal Dashboard",
  description: "Institutional real-time BTC research, quantitative SBR-5 trading signals, and statistical AI forecasting dashboard for Delta Exchange India.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full dark antialiased">
      <body className="min-h-full flex flex-col bg-[#07090e] text-[#ededed]">{children}</body>
    </html>
  );
}
