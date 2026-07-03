/**
 * Chart colors resolved from the design-system CSS variables in globals.css, so
 * lightweight-charts (which paints to canvas and can't read CSS) follows the active
 * theme. Fallbacks mirror the dark palette for non-browser contexts.
 */
export type ChartTheme = {
  text: string;
  grid: string;
  border: string;
  up: string;
  down: string;
  line: string;
};

export function readChartTheme(): ChartTheme {
  const styles = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback;
  return {
    text: read("--muted-foreground", "#8b95a4"),
    grid: read("--border", "#1e2632"),
    border: read("--border", "#1e2632"),
    up: read("--profit", "#1fd6a3"),
    down: read("--loss", "#ff5a6a"),
    line: read("--primary", "#4f8cff"),
  };
}

/**
 * A stable, colorblind-friendly palette for indicator lines, keyed so a given
 * indicator series always paints the same color (chart + panel swatch stay in
 * sync). These are the ONLY place indicator colors are defined — components must
 * read them from here, never hardcode hex (invariant: route colors through
 * chart-theme.ts). Values are fixed hex (canvas can't read CSS vars); the
 * accent/profit/loss ones mirror the design-system defaults.
 */
export const INDICATOR_COLORS: Record<string, string> = {
  EMA: "#4f8cff", // primary blue
  SMA: "#f5a524", // amber
  VWAP: "#a86bff", // violet
  "BBANDS:upper": "#1fd6a3", // profit green
  "BBANDS:middle": "#8b95a4", // muted
  "BBANDS:lower": "#ff5a6a", // loss red
  RSI: "#4f8cff",
  ATR: "#f5a524",
  "MACD:macd": "#4f8cff",
  "MACD:signal": "#f5a524",
  "MACD:hist": "#8b95a4",
};

/** Color for a given indicator series key (`<type>` or `<type>:<output>`). */
export function indicatorColor(type: string, output = "value"): string {
  return (
    INDICATOR_COLORS[output === "value" ? type : `${type}:${output}`] ??
    INDICATOR_COLORS[type] ??
    "#8b95a4"
  );
}

/** Calls `cb` whenever the theme class on <html> flips; returns an unsubscribe. */
export function onThemeChange(cb: () => void): () => void {
  const observer = new MutationObserver(cb);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
}
