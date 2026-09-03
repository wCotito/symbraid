const fs = require('fs');
const path = require('path');

function isFile(candidate, fsImpl = fs) {
  try {
    if (typeof fsImpl.statSync === 'function') return fsImpl.statSync(candidate).isFile();
    return Boolean(fsImpl.existsSync(candidate));
  } catch (_) {
    return false;
  }
}

function pathCandidates(command, env, platform, pathApi) {
  const pathValue = String(env.PATH || '');
  if (!pathValue) return [];
  const directories = pathValue.split(platform === 'win32' ? ';' : path.delimiter).filter(Boolean);
  if (platform !== 'win32') return directories.map((directory) => pathApi.join(directory, command));

  const extensions = String(env.PATHEXT || '.COM;.EXE;.BAT;.CMD')
    .split(';')
    .filter(Boolean);
  const names = [command, ...extensions.map((extension) => `${command}${extension.toLowerCase()}`)];
  return directories.flatMap((directory) => names.map((name) => pathApi.join(directory, name)));
}

function resolveExecutablePath(configuredPath = '', options = {}) {
  const env = options.env || process.env;
  const platform = options.platform || process.platform;
  const fsImpl = options.fs || fs;
  const pathApi = platform === 'win32' ? path.win32 : path;
  const configured = typeof configuredPath === 'string' ? configuredPath.trim() : '';
  if (configured) return configured;

  for (const candidate of pathCandidates('symbraid', env, platform, pathApi)) {
    if (isFile(candidate, fsImpl)) return candidate;
  }

  return 'symbraid';
}

module.exports = { resolveExecutablePath };
