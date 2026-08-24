/**
 * Attribution notice required by the Lightweight Charts™ licence (Apache-2.0 plus
 * TradingView's attribution term): products built on the library have to carry a
 * visible notice linking back to TradingView.
 *
 * It is a link, not a badge, and it deliberately does not imply endorsement — we
 * license their charting library, nothing more. Rendered in the footer of every
 * surface that draws a chart, plus the third-party notices on /methodology.
 */
export function ChartAttribution({ className }: { className?: string }) {
  return (
    <a
      href="https://www.tradingview.com/"
      target="_blank"
      rel="noopener noreferrer"
      className={className ?? "transition-colors hover:text-foreground"}
    >
      Charts by TradingView Lightweight Charts&trade;
    </a>
  );
}
