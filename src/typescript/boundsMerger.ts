/**
 * Bounds Merger - challenge implementation.
 *
 * Processes matched bounds from the Python matcher for the PDF
 * visualization overlay:
 *  1. Validates and loads match results.
 *  2. Converts normalized (0-1) bounds to pixel coordinates.
 *  3. Detects overlapping bounds (IoU) and merges them into single boxes.
 *  4. Adds per-entity-type colors for the React overlay component.
 */

import type {
  Bounds,
  MatchedEntity,
  MatchResult,
  PixelBounds,
  MergedBounds,
  PDFDimensions,
} from './types';

/**
 * Configuration for bounds merging.
 */
interface MergerConfig {
  overlapThreshold: number; // Minimum IoU to merge (0-1)
  confidenceThreshold: number; // Minimum confidence to include
  colorScheme: Record<string, string>; // Entity type -> color mapping
}

const DEFAULT_CONFIG: MergerConfig = {
  overlapThreshold: 0.3,
  confidenceThreshold: 0.1,
  colorScheme: {
    KPI: '#4CAF50',
    DATE: '#2196F3',
    ORGANIZATION: '#FF9800',
    default: '#9E9E9E',
  },
};

/**
 * BoundsMerger class - processes matched entities for visualization.
 */
export class BoundsMerger {
  private results: MatchResult | null = null;
  private config: MergerConfig;
  private pdfDimensions: PDFDimensions | null = null;

  constructor(config: Partial<MergerConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * Validate and load match results from JSON.
   */
  loadResults(jsonData: MatchResult): void {
    if (!jsonData || !Array.isArray(jsonData.matched_entities)) {
      throw new Error('Invalid match results: missing matched_entities array');
    }
    for (const entity of jsonData.matched_entities) {
      if (
        typeof entity.entity_name !== 'string' ||
        typeof entity.confidence !== 'number'
      ) {
        throw new Error('Invalid match results: malformed entity entry');
      }
    }
    this.results = jsonData;
  }

  /**
   * Set the PDF dimensions for coordinate conversion.
   */
  setPDFDimensions(dimensions: PDFDimensions): void {
    this.pdfDimensions = dimensions;
  }

  /**
   * Convert normalized bounds (0-1) to pixel coordinates.
   *
   * pixel_x = normalized_x * page_width * scale, etc.
   *
   * @param bounds - Normalized bounds from Python
   * @returns Pixel bounds for SVG rendering
   */
  convertToPixels(bounds: Bounds): PixelBounds {
    if (!this.pdfDimensions) {
      throw new Error('PDF dimensions not set');
    }
    const { width, height, scale } = this.pdfDimensions;
    const round2 = (n: number): number => Math.round(n * 100) / 100;
    return {
      page: bounds.page,
      x: round2(bounds.x * width * scale),
      y: round2(bounds.y * height * scale),
      width: round2(bounds.width * width * scale),
      height: round2(bounds.height * height * scale),
    };
  }

  /**
   * Intersection-over-union of two pixel bounds.
   *
   * Bounds on different pages never overlap.
   *
   * @returns Overlap ratio (0-1)
   */
  calculateOverlap(a: PixelBounds, b: PixelBounds): number {
    if (a.page !== b.page) {
      return 0;
    }
    const x0 = Math.max(a.x, b.x);
    const y0 = Math.max(a.y, b.y);
    const x1 = Math.min(a.x + a.width, b.x + b.width);
    const y1 = Math.min(a.y + a.height, b.y + b.height);

    const interWidth = Math.max(0, x1 - x0);
    const interHeight = Math.max(0, y1 - y0);
    const intersection = interWidth * interHeight;
    if (intersection === 0) {
      return 0;
    }

    const union =
      a.width * a.height + b.width * b.height - intersection;
    return union === 0 ? 0 : intersection / union;
  }

  /**
   * Merge bounds into the smallest single box containing all of them.
   *
   * @param boundsArray - Array of bounds to merge (same page expected)
   * @returns Encompassing pixel bounds
   */
  mergeBounds(boundsArray: PixelBounds[]): PixelBounds {
    if (boundsArray.length === 0) {
      throw new Error('Cannot merge empty bounds array');
    }
    const x0 = Math.min(...boundsArray.map((b) => b.x));
    const y0 = Math.min(...boundsArray.map((b) => b.y));
    const x1 = Math.max(...boundsArray.map((b) => b.x + b.width));
    const y1 = Math.max(...boundsArray.map((b) => b.y + b.height));
    const round2 = (n: number): number => Math.round(n * 100) / 100;
    return {
      page: boundsArray[0].page,
      x: round2(x0),
      y: round2(y0),
      width: round2(x1 - x0),
      height: round2(y1 - y0),
    };
  }

  /**
   * Get color for entity type.
   */
  getEntityColor(entityType: string): string {
    return this.config.colorScheme[entityType] || this.config.colorScheme.default;
  }

  /**
   * Group pixel bounds by page, then greedily merge pairs whose IoU
   * meets the overlap threshold (union-find, so merge chains collapse).
   */
  private mergeOverlaps(
    items: Array<{ entity: MatchedEntity; pixels: PixelBounds }>
  ): Array<{ entity: MatchedEntity; pixels: PixelBounds }> {
    // Union-find over item indices.
    const parent = items.map((_, i) => i);
    const find = (i: number): number => {
      while (parent[i] !== i) {
        parent[i] = parent[parent[i]];
        i = parent[i];
      }
      return i;
    };
    const union = (i: number, j: number): void => {
      parent[find(i)] = find(j);
    };

    for (let i = 0; i < items.length; i++) {
      for (let j = i + 1; j < items.length; j++) {
        if (
          this.calculateOverlap(items[i].pixels, items[j].pixels) >=
          this.config.overlapThreshold
        ) {
          union(i, j);
        }
      }
    }

    const groups = new Map<number, number[]>();
    items.forEach((_, i) => {
      const root = find(i);
      if (!groups.has(root)) {
        groups.set(root, []);
      }
      groups.get(root)!.push(i);
    });

    return [...groups.values()].map((indices) => {
      const pixels = this.mergeBounds(indices.map((i) => items[i].pixels));
      const names = indices.map((i) => items[i].entity.entity_name);
      const best = indices.reduce((a, b) =>
        items[a].entity.confidence >= items[b].entity.confidence ? a : b
      );
      const mergedEntity: MatchedEntity = {
        ...items[best].entity,
        entity_name: names.join(' + '),
        confidence: Math.max(
          ...indices.map((i) => items[i].entity.confidence)
        ),
      };
      return { entity: mergedEntity, pixels };
    });
  }

  /**
   * Process all matched entities and return visualization-ready data.
   *
   * Pipeline: confidence filter -> pixel conversion -> page grouping ->
   * overlap merging -> color assignment.
   *
   * @returns Array of merged bounds ready for SVG rendering
   */
  getVisualizationData(): MergedBounds[] {
    if (!this.results) {
      throw new Error('No results loaded');
    }

    const converted: Array<{ entity: MatchedEntity; pixels: PixelBounds }> = [];
    for (const entity of this.results.matched_entities) {
      if (entity.confidence < this.config.confidenceThreshold) {
        continue;
      }
      if (!entity.bounds) {
        continue;
      }
      converted.push({
        entity,
        pixels: this.convertToPixels(entity.bounds),
      });
    }

    // Merge overlaps within each page.
    const byPage = new Map<number, typeof converted>();
    for (const item of converted) {
      const page = item.pixels.page;
      if (!byPage.has(page)) {
        byPage.set(page, []);
      }
      byPage.get(page)!.push(item);
    }

    const visualData: MergedBounds[] = [];
    for (const pageItems of byPage.values()) {
      for (const { entity, pixels } of this.mergeOverlaps(pageItems)) {
        visualData.push({
          entity_name: entity.entity_name,
          pixel_bounds: pixels,
          confidence: entity.confidence,
          color: this.getEntityColor(entity.entity_type),
        });
      }
    }

    return visualData;
  }
}

/**
 * Utility function to load and process results in one call.
 */
export function processMatchResults(
  jsonData: MatchResult,
  pdfDimensions: PDFDimensions,
  config?: Partial<MergerConfig>
): MergedBounds[] {
  const merger = new BoundsMerger(config);
  merger.loadResults(jsonData);
  merger.setPDFDimensions(pdfDimensions);
  return merger.getVisualizationData();
}

export { DEFAULT_CONFIG };
export type { MergerConfig };
