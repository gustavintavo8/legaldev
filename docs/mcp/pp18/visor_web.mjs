// Pinta Markdown con el visor de la web (marked + DOMPurify, src/lib/markdown.ts de
// legaldev-web) y devuelve, por cada texto, el HTML, el src de las imágenes, el href de los
// enlaces (con el host que resuelve el navegador) y los demás elementos que pueden cargar algo
// solos (con style, background, src, srcset o poster). Lo usa oraculo.py. Uso:
// node visor_web.mjs <ruta de legaldev-web>  (JSON por stdin y stdout: una lista de cadenas;
// una lista de {html, imgs, links, cargas}). Solo lee: resuelve los paquetes desde el
// package.json de legaldev-web y no escribe nada. Usa una sola ventana de JSDOM para todos los
// textos, así que miles de casos de los fuzzers se pintan en unos segundos.
import { createRequire } from 'node:module';
import path from 'node:path';

const web = process.argv[2];
const require = createRequire(path.resolve(web, 'package.json'));
const { marked } = require('marked');
const createDOMPurify = require('dompurify');
const { JSDOM } = require('jsdom');
const DOMPurify = createDOMPurify(new JSDOM('').window);
const documento = new JSDOM('<!doctype html><body></body>').window.document;

let entrada = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (trozo) => (entrada += trozo));
process.stdin.on('end', () => {
  const salida = JSON.parse(entrada).map((md) => {
    const html = DOMPurify.sanitize(marked.parse(md, { async: false }));
    const raiz = documento.createElement('div');
    raiz.innerHTML = html;
    return {
      html,
      imgs: [...raiz.querySelectorAll('img')].map((e) => e.getAttribute('src')),
      // El href y el host que resuelve el navegador (con «www.boe.es%C2%A0"@otro» el host
      // es «otro», y el texto del href engaña).
      links: [...raiz.querySelectorAll('a')].map((e) => {
        const href = e.getAttribute('href');
        try {
          const url = new URL(href, 'https://legaldev.invalid/');
          return { href, host: url.hostname, usuario: url.username, protocolo: url.protocol };
        } catch {
          return { href, host: null, usuario: '', protocolo: null };
        }
      }),
      cargas: [...raiz.querySelectorAll('[style],[background],[src],[srcset],[poster]')]
        .filter((e) => e.tagName !== 'IMG')
        .map((e) => e.outerHTML.slice(0, 120)),
      // Texto fuera de <pre> y <code>: para comprobar que las secciones que añade el código
      // detrás del texto del modelo no acaban dentro de un bloque de código.
      fuera_de_codigo: (() => {
        const copia = raiz.cloneNode(true);
        copia.querySelectorAll('pre, code').forEach((e) => e.remove());
        return copia.textContent;
      })(),
    };
  });
  process.stdout.write(JSON.stringify(salida));
});
