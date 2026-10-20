import assert from 'node:assert/strict';
import test from 'node:test';
import { trustedOrigin, validSha, ciForRevision, needsUpdate } from './updater-policy.mjs';

const sha = '0123456789abcdef0123456789abcdef01234567';
const run = { id: 21, name: 'CI', path: '.github/workflows/ci.yml@refs/heads/main', head_sha: sha, event: 'push', head_branch: 'main', status: 'completed', conclusion: 'success' };

test('Разрешён только собственный GitHub-репозиторий', () => {
  assert.equal(trustedOrigin('https://github.com/Aspksa/Meiyuren.git'), true);
  assert.equal(trustedOrigin('git@github.com:Aspksa/Meiyuren.git'), true);
  assert.equal(trustedOrigin('https://evil.example/Aspksa/Meiyuren.git'), false);
  assert.equal(trustedOrigin('https://github.com/other/repo.git'), false);
});

test('Проверка SHA не принимает произвольные аргументы для git', () => {
  assert.equal(validSha(sha), true);
  assert.equal(validSha('--hard HEAD'), false);
});

test('Разрешена лишь завершённая и успешная CI в main для нужного коммита', () => {
  assert.equal(ciForRevision([run], sha), 'success');
  assert.equal(ciForRevision([{...run, status:'in_progress'}], sha), 'pending');
  assert.equal(ciForRevision([{...run, conclusion:'failure'}], sha), 'failed');
  assert.equal(ciForRevision([{...run, head_sha:'f'.repeat(40)}], sha), 'missing');
  assert.equal(ciForRevision([{...run, event:'pull_request'}], sha), 'missing');
  assert.equal(ciForRevision([{...run, path: '.github/workflows/other.yml'}], sha), 'missing');
});

test('Автоматическая установка блокируется при незавершённых тестах или локальных изменениях', () => {
  assert.equal(needsUpdate('a'.repeat(40), sha, 'success', true, true, 'main'), true);
  assert.equal(needsUpdate(sha, sha, 'success', true, true, 'main'), false);
  assert.equal(needsUpdate('a'.repeat(40), sha, 'pending', true, true, 'main'), false);
  assert.equal(needsUpdate('a'.repeat(40), sha, 'success', false, true, 'main'), false);
  assert.equal(needsUpdate('a'.repeat(40), sha, 'success', true, false, 'main'), false);
  assert.equal(needsUpdate('a'.repeat(40), sha, 'success', true, true, 'feature'), false);
});
