// Shared DOM builders, translated labels, action errors, and formatting.
const t = window.Locale.t;

const $ = id => document.getElementById(id);

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child);
  return node;
}

function error(message) { $('error').textContent = t(message); $('error').hidden = false; $('health').textContent = t(message); }

function action(fn) { return async event => { try { await fn(event); } catch (e) { error(e.message); } }; }

function button(text, fn, cls = 'secondary small-button') { return window.Locale.bind(el('button', {type: 'button', class: cls, onclick: action(fn)}), text); }

function link(text, href, download = false) { return window.Locale.bind(el('a', {href, ...(download ? {download: ''} : {target: '_blank', rel: 'noopener noreferrer'})}), text); }

function bytes(value) { return value == null ? t('N/A') : `${(value / 1073741824).toFixed(2)} GiB`; }

function formatTransferBytes(value) {
  if (!Number.isFinite(value) || value < 0) return 'N/A';
  if (value < 1024) return Math.round(value) + ' B';
  if (value < 1048576) return (value / 1024).toFixed(1) + ' KiB';
  if (value < 1073741824) return (value / 1048576).toFixed(1) + ' MiB';
  return (value / 1073741824).toFixed(2) + ' GiB';
}

function duration(value) { const n = Math.max(0, value || 0); return `${String(Math.floor(n / 60)).padStart(2, '0')}:${(n % 60).toFixed(1).padStart(4, '0')}`; }

export {$, action, button, bytes, duration, el, error, formatTransferBytes, link, sleep, t};
