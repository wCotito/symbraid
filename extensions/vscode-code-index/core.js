const path = require('path');

const supportedExtensions = new Set([
  '.py', '.pyi', '.js', '.mjs', '.cjs', '.jsx', '.ts', '.mts', '.cts', '.tsx',
  '.rs', '.go', '.java', '.c', '.h', '.cc', '.cpp', '.cxx', '.hpp', '.hh', '.cs',
  '.rb', '.php', '.kt', '.kts', '.swift', '.scala', '.sh', '.md', '.mdx', '.rst',
  '.txt', '.json', '.jsonl', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.sql',
  '.graphql', '.gql', '.html', '.htm', '.css', '.scss', '.less', '.vue', '.svelte',
  '.ps1', '.bat', '.cmd', '.dockerfile'
]);

const excludedSegments = new Set([
  '.git', 'node_modules', 'vendor', 'dist', 'build', 'target', 'coverage', '.next',
  '.nuxt', '.venv', 'venv', '__pycache__'
]);

const excludedNames = new Set([
  'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock'
]);

function normalizeFsPath(value) {
  const resolved = path.resolve(value);
  return process.platform === 'win32' ? resolved.toLowerCase() : resolved;
}

function eventKind(relativePath) {
  const normalized = relativePath.replace(/\\/g, '/');
  const segments = normalized.split('/').filter(Boolean);
  const name = (segments.at(-1) || '').toLowerCase();
  if (name === '.gitignore' || name === '.ignore') {
    return 'reconcile';
  }
  if (segments.some((segment) => excludedSegments.has(segment.toLowerCase()))) {
    return 'ignore';
  }
  if (excludedNames.has(name) || name.endsWith('.min.js') || name.endsWith('.map')) {
    return 'ignore';
  }
  if (name === 'dockerfile' || supportedExtensions.has(path.extname(name))) {
    return 'refresh';
  }
  return 'ignore';
}

function headChanged(previous, current) {
  return Boolean(previous && current && previous !== current);
}

module.exports = { eventKind, headChanged, normalizeFsPath };
