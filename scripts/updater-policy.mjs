export const REPOSITORY = 'Aspksa/Meiyuren';
export const REPOSITORY_GIT = 'https://github.com/Aspksa/Meiyuren.git';
export const GITHUB_PAGE = 'https://github.com/Aspksa/Meiyuren';

export function trustedOrigin(value) {
  return /^(?:https:\/\/github\.com\/Aspksa\/Meiyuren(?:\.git)?|git@github\.com:Aspksa\/Meiyuren(?:\.git)?|ssh:\/\/git@github\.com\/Aspksa\/Meiyuren(?:\.git)?)$/i.test(value.trim());
}

export function validSha(value) {
  return typeof value === 'string' && /^[a-f0-9]{40}$/i.test(value);
}

export function ciForRevision(runs, sha) {
  if (!validSha(sha) || !Array.isArray(runs)) return 'missing';
  const matching = runs.filter((run) =>
    run.head_sha === sha &&
    run.event === 'push' &&
    run.head_branch === 'main' &&
    run.name === 'CI' &&
    typeof run.path === 'string' &&
    run.path.split('@')[0] === '.github/workflows/ci.yml'
  );
  if (matching.length === 0) return 'missing';
  const newest = matching.reduce((a, b) => Number(a.id) > Number(b.id) ? a : b);
  if (newest.status !== 'completed') return 'pending';
  return newest.conclusion === 'success' ? 'success' : 'failed';
}

export function needsUpdate(localSha, remoteSha, ciState, clean, trusted, branch) {
  return validSha(localSha) && validSha(remoteSha) && localSha !== remoteSha &&
    ciState === 'success' && clean && trusted && branch === 'main';
}
