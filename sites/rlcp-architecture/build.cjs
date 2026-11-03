const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

function buildHtml() {
  const read = name => fs.readFileSync(path.join(__dirname, 'src', name), 'utf8').replace(/\r\n/g, '\n');
  let html = read('index.html');
  const css = read('style.css');
  const scripts = ['model.js', 'app.js'].map(read).join('\n;\n');
  assert(!/<\/style/i.test(css), 'Styles contain an HTML closing tag');
  assert(!/<\/script/i.test(scripts), 'Scripts contain an HTML closing tag');
  const stylesheet = '<link rel="stylesheet" href="style.css">';
  const scriptTags = '<script defer src="model.js"></script><script defer src="app.js"></script>';
  assert(html.includes(stylesheet) && html.includes(scriptTags), 'Source asset tags changed');
  assert.equal((html.match(/<!-- FULL_ONLY_START -->/g) || []).length, 3);
  assert.equal((html.match(/<!-- FULL_ONLY_END -->/g) || []).length, 3);
  html = html.replace(/<!-- FULL_ONLY_START -->[\s\S]*?<!-- FULL_ONLY_END -->/g, '')
    .replace(stylesheet, () => `<style>\n${css}\n</style>`)
    .replace(scriptTags, '')
    .replace(/^[ \t]+$/gm, '')
    // Inline scripts run after the DOM exists; defer only applies to external scripts.
    .replace('</body>', () => `<script>\n${scripts}\n</script>\n</body>`);
  assert(!/<(?:script|link)\b[^>]*(?:src|href)=/i.test(html), 'Output still depends on external assets');
  return html;
}

if (require.main === module) {
  fs.mkdirSync(path.join(__dirname, 'dist'), { recursive: true });
  fs.writeFileSync(path.join(__dirname, 'dist/index.html'), buildHtml(), 'utf8');
  console.log('Built dist/index.html: standalone interactive architecture diagram.');
}
module.exports = buildHtml;
