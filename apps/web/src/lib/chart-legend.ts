import type {
  CandlestickData,
  IChartApi,
  ISeriesApi,
  MouseEventParams,
  Time,
} from "lightweight-charts";

import { readChartTheme } from "./chart-theme";

const fmt = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });

/**
 * Attaches a TradingView-style OHLC legend that tracks the crosshair and falls
 * back to the latest bar when the cursor leaves the chart. Shared by the public
 * per-ticker chart and the authenticated workspace so the two never drift.
 *
 * Returns `setLatest` (call it when new/streamed data arrives so the resting
 * legend stays current) and `dispose` for effect cleanup.
 */
export function attachOhlcLegend(
  chart: IChartApi,
  series: ISeriesApi<"Candlestick">,
  el: HTMLElement,
) {
  let latest: CandlestickData | null = null;

  const render = (candle: CandlestickData | null) => {
    const d = candle ?? latest;
    if (!d) {
      el.innerHTML = "";
      return;
    }
    const theme = readChartTheme();
    const color = d.close >= d.open ? theme.up : theme.down;
    el.innerHTML =
      `<span class="opacity-50">O</span> ${fmt(d.open)}` +
      `  <span class="opacity-50">H</span> ${fmt(d.high)}` +
      `  <span class="opacity-50">L</span> ${fmt(d.low)}` +
      `  <span class="opacity-50">C</span> <span style="color:${color};font-weight:600">${fmt(d.close)}</span>`;
  };

  const handler = (param: MouseEventParams<Time>) => {
    const candle = (param.seriesData.get(series) as CandlestickData | undefined) ?? null;
    render(candle);
  };

  chart.subscribeCrosshairMove(handler);

  return {
    setLatest(candle: CandlestickData | null) {
      latest = candle;
      render(null);
    },
    dispose() {
      chart.unsubscribeCrosshairMove(handler);
    },
  };
}
