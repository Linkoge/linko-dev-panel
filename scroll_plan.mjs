/** Choose the next real browser scroll position. Tall sticky stages get closer samples. */
export function nextScrollPosition(current, bottom, viewportHeight, overlap, regions) {
  const step = Math.max(1, Math.round(viewportHeight * (1 - overlap / 100)));
  let next = current + step;
  for (const region of regions) {
    if (current < region.top && region.top < next) next = region.top;
    if (current >= region.top && current < region.end) {
      next = Math.min(next, current + Math.round(viewportHeight * 0.5), region.end);
    }
  }
  return Math.min(bottom, Math.max(current + 1, next));
}
