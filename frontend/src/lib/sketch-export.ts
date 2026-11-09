/**
 * Sizing for sketch -> PNG export. Small doodles are scaled up so the image is legible to the
 * extraction model and clears the backend minimum (32px per side); huge canvases are capped well
 * under the backend maximum (12000px per side, 40 MP).
 */

export const MIN_SHORT_SIDE = 512;
export const MAX_LONG_SIDE = 4096;

export function exportDimensions(
  width: number,
  height: number,
): { width: number; height: number; scale: number } {
  const short = Math.max(1, Math.min(width, height));
  const long = Math.max(1, width, height);
  let scale = Math.max(1, MIN_SHORT_SIDE / short);
  scale = Math.min(scale, MAX_LONG_SIDE / long); // the cap wins for very long, thin drawings
  return { width: Math.round(width * scale), height: Math.round(height * scale), scale };
}

export function sketchFileName(now: Date = new Date()): string {
  const stamp = now.toISOString().replace(/[:.]/g, "-").slice(0, 19);
  return `sketch-${stamp}.png`;
}
