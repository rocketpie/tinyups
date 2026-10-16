// Print a puppeteer launch-options JSON for mermaid-cli, using the Chromium
// that ships as an npm tarball (@sparticuz/chromium — the Google storage
// endpoint is unreachable from this container, but the npm registry is not).
//
//   node engines/mmconf.mjs > /tmp/mm-puppeteer.json
//   mmdc -p /tmp/mm-puppeteer.json -i build/layout/graph.mmd -o build/layout/mermaid.svg
import chromium from "@sparticuz/chromium";

const executablePath = await chromium.executablePath();
process.stdout.write(JSON.stringify({
  executablePath,
  args: [...chromium.args, "--no-sandbox", "--disable-setuid-sandbox"],
  headless: true,
}));
