'use strict';

function errorPayload(error) {
  return { status: 'error', error: error instanceof Error ? error.message : String(error) };
}

async function loadManageState(runCli, cwd) {
  let state;
  try {
    state = await runCli(['settings', 'show', '--project', cwd], cwd);
  } catch (error) {
    return {
      status: 'error',
      project: { path: cwd, index_status: errorPayload(error) },
    };
  }
  const project = state && typeof state.project === 'object' ? state.project : undefined;
  const indexStatus = project?.index_status;
  if (project && (!indexStatus || (typeof indexStatus === 'object' && !Object.keys(indexStatus).length))) {
    try {
      project.index_status = await runCli(['status', cwd], cwd);
    } catch (error) {
      project.index_status = errorPayload(error);
    }
  }
  return state;
}

module.exports = { loadManageState };