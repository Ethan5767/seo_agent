export const metadata = {
  title: "SEO/AEO Pipeline — Scan",
  description: "Audit a URL for SEO, AEO, and performance; fix it or brief it.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ font: "15px system-ui", maxWidth: 820, margin: "2rem auto", padding: "0 1rem", color: "#111" }}>
        {children}
      </body>
    </html>
  );
}
