import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Gulzar } from "next/font/google";
import { AppShell } from "@/components/AppShell";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
// Gulzar: a clear Nastaliq designed in the style of Noori Nastaliq.
const urdu = Gulzar({ variable: "--font-urdu", subsets: ["arabic"], weight: "400" });

export const metadata: Metadata = {
  title: "Junior Muneer",
  description: "Your personal AI assistant and friend",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

// Applies the saved theme before the first paint, so there's no flash.
const themeScript = `(function(){try{var t=localStorage.getItem("theme");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}})()`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} ${urdu.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="h-full">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
