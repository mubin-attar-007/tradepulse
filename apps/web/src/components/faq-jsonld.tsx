/**
 * Emits a schema.org FAQPage JSON-LD blob for a list of Q&A pairs. Server-safe
 * (renders a plain <script> tag) and reused by the public per-ticker pages so the
 * on-page FAQ and the structured data never drift.
 *
 * Honesty note: the answers passed in must match the visible FAQ copy — do not
 * put claims in structured data that aren't also shown to the user.
 */
export type FaqItem = { question: string; answer: string };

export function FaqJsonLd({ items }: { items: FaqItem[] }) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: { "@type": "Answer", text: item.answer },
    })),
  };
  return (
    <script
      type="application/ld+json"
      // JSON.stringify output is safe to inline; no user-controlled HTML.
      dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
    />
  );
}
