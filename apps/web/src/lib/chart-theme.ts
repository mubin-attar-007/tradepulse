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

/** Calls `cb` whenever the theme class on <html> flips; returns an unsubscribe. */
export function onThemeChange(cb: () => void): () => void {
  const observer = new MutationObserver(cb);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
}
