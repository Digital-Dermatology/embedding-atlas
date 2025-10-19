// Copyright (c) 2025 Apple Inc. Licensed under MIT License.

import { rgb } from "d3-color";

const category10 = [
  "#E65050",
  "#E6AA50",
  "#C8E650",
  "#6EE650",
  "#50E68C",
  "#50E6E6",
  "#508CE6",
  "#6E50E6",
  "#C850E6",
  "#E650AA",
];

const category20 = [
  "#E65050",
  "#E67D50",
  "#E6AA50",
  "#E6D750",
  "#C8E650",
  "#9BE650",
  "#6EE650",
  "#50E65F",
  "#50E68C",
  "#50E6B9",
  "#50E6E6",
  "#50B9E6",
  "#508CE6",
  "#505FE6",
  "#6E50E6",
  "#9B50E6",
  "#C850E6",
  "#E650D7",
  "#E650AA",
  "#E6507D",
];

export function defaultCategoryColors(count: number): string[] {
  if (count < 1) {
    count = 1;
  }
  if (count <= category10.length) {
    return category10.slice(0, count);
  } else if (count <= category20.length) {
    return category20.slice(0, count);
  } else {
    let colors: string[] = [];
    for (let i = 0; i < count; i++) {
      colors[i] = category20[i % category20.length];
    }
    return colors;
  }
}

/** Parse color string into normalized sRGB values (all between 0 and 1). */
export function parseColorNormalizedRgb(str: string): { r: number; g: number; b: number; a: number } {
  let { r, g, b, opacity } = rgb(str);
  return { r: r / 255.0, g: g / 255.0, b: b / 255.0, a: opacity };
}
