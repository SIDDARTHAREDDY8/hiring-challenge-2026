import * as fs from 'fs';
import { processMatchResults } from '../../../src/typescript/boundsMerger';
test('real pipeline output converts cleanly', () => {
  const data = JSON.parse(fs.readFileSync('output/matched_bounds.json', 'utf8'));
  const vis = processMatchResults(data, { width: 612, height: 792, scale: 1.5 });
  console.log(JSON.stringify(vis.slice(0, 2), null, 1));
  expect(vis.length).toBe(7);
  for (const v of vis) {
    expect(v.pixel_bounds.x).toBeGreaterThanOrEqual(0);
    expect(v.pixel_bounds.page).toBeGreaterThanOrEqual(1);
  }
});
