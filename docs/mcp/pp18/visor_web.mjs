// Pinta Markdown con el visor de la web (marked + DOMPurify, src/lib/markdown.ts de
// legaldev-web) y devuelve, por cada texto, el src de las imágenes y el href de los enlaces.
// Lo usa visor_web.py. Uso: node visor_web.mjs <ruta de legaldev-web>  (JSON por stdin y stdout:
// una lista de cadenas; una lista de {imgs, links}). Solo lee: resuelve los paquetes desde el
// package.json de legaldev-web y no escribe nada.
import { createRequire } from 'node:module';
import path from 'node:path';

const web = process.argv[2];
const require = createRequire(path.resolve(web, 'package.json'));
const { marked } = require('marked');
const createDOMPurify = require('dompurify');
const { JSDOM } = require('jsdom');
const DOMPurify = createDOMPurify(new JSDOM('').window);

let entrada = '';
process.stdin.on('data', (trozo) => (entrada += trozo));
process.stdin.on('end', () => {
  const salida = JSON.parse(entrada).map((md) => {
    const html = DOMPurify.sanitize(marked.parse(md, { async: false }));
    const doc = new JSDOM(html).window.document;
    return {
      imgs: [...doc.querySelectorAll('img')].map((e) => e.getAttribute('src')),
      links: [...doc.querySelectorAll('a')].map((e) => e.getAttribute('href')),
    };
  });
  process.stdout.write(JSON.stringify(salida));
});
