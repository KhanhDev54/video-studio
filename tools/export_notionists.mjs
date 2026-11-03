// Xuất bộ hình Notionists (thiết kế: Zoish, giấy phép CC0 1.0; mã DiceBear: MIT) thành JSON
// để app ráp nhân vật bằng Python + QtSvg, không cần Node khi chạy.
//
//   npm install @dicebear/core@9.4.2 @dicebear/notionists@9.4.2
//   node tools/export_notionists.mjs > video_studio/assets/notionists.json
import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';
import * as notionists from '@dicebear/notionists';

const require = createRequire(import.meta.url);
const lib = path.dirname(require.resolve('@dicebear/notionists'));
const index = fs.readFileSync(path.join(lib, 'index.js'), 'utf8');
const viewBox = index.match(/viewBox: '([^']+)'/)[1];
const layers = [...index.matchAll(/<g transform="(translate\([-0-9 ]+\))">\$\{\(_\w = \(_\w = components\.(\w+)/g)]
  .map(([, transform, group]) => ({ group, transform }));

// Thành phần lồng nhau và màu được thay bằng chỗ trống {{tên}} để Python điền vào.
const stub = new Proxy({}, { get: (_, key) => ({ value: () => `{{${String(key)}}}` }) });
const components = {};
const groups = layers.map((l) => l.group);
for (const group of groups) {
  const mod = await import(path.join(lib, 'components', `${group}.js`));
  const variants = Object.values(mod)[0];
  components[group] = Object.fromEntries(
    Object.entries(variants).map(([name, fn]) => [name, fn(stub, stub)]));
  // thành phần lồng bên trong (vd. bodyIcon trong body)
  for (const [, nested] of JSON.stringify(components[group]).matchAll(/\{\{(\w+)\}\}/g))
    if (!groups.includes(nested)) groups.push(nested);
}

const schema = notionists.schema.properties;
const probability = Object.fromEntries(Object.entries(schema)
  .filter(([k]) => k.endsWith('Probability')).map(([k, v]) => [k, v.default]));

process.stdout.write(JSON.stringify({
  meta: { ...notionists.meta, code_license: 'MIT (DiceBear, Florian Körner)' },
  viewBox, layers, components, probability,
}));
