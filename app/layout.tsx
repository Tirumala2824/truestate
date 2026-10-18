import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./responsive.css";

export const viewport: Viewport = {width:"device-width",initialScale:1,viewportFit:"cover",interactiveWidget:"resizes-content"};

export const metadata: Metadata = {
  title: "TRUESTATE | Financial clarity. Just ask.",
  description: "Investigate payments, understand evidence, and review risk in one conversation. Synthetic guided demonstration.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
