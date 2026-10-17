'use strict';

function errorPayload(error) {
  return { status: 'error', error: error instanceof Error ? error.message : String(error) };
}

async function loadManageState(runCli, cwd) {
  let state;
  try {
    state = await runCli(['settings', 'show', '--project', cwd], cwd);
  } catch (error) {
    let globalState = {};
    try {
      globalState = await runCli(['settings', 'show'], cwd);
    } catch (_) {
      // Keep the original project error if global settings are also unavailable.
    }
    return {
      ...globalState,
      status: 'error',
      profiles: Object.fromEntries(Object.entries(globalState.profiles || {})
        .filter(([, profile]) => profile.scope !== 'project')),
      project: { path: cwd, index_status: errorPayload(error) },
    };
  }
  const project = state && typeof state.project === 'object' ? state.project : undefined;
  const indexStatus = project?.index_status;
  if (project && project.registered !== false && (!indexStatus || (typeof indexStatus === 'object' && !Object.keys(indexStatus).length))) {
    try {
      project.index_status = await runCli(['status', cwd], cwd);
    } catch (error) {
      project.index_status = errorPayload(error);
    }
  }
  return state;
}

module.exports = { loadManageState };
