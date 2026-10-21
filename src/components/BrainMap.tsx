import { useEffect, useState } from 'react';
import { decideBrainProposal, getBrainMap, removeCustomBrain } from '../services/chatApi';
import type { BrainMap as BrainMapData, MemoryBrain } from '../services/chatApi';

/** Карта мозгов: как они выросли за неделю, какие ветки сильные, какие засыпают. */
export function BrainMap({ active, version, names, onChange }: {
  active: boolean; version: number; names: Record<MemoryBrain, string>; onChange: () => void;
}) {
  const [map, setMap] = useState<BrainMapData | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!active) return;
    void getBrainMap().then(setMap).catch(() => undefined);
  }, [active, version]);

  async function act(work: () => Promise<unknown>) {
    setBusy(true);
    try {
      await work();
      setMap(await getBrainMap());
      setError('');
      onChange();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось изменить мозги');
    } finally {
      setBusy(false);
    }
  }

  if (!map) return null;
  const title = (id: string, custom: string | null) => custom ?? names[id as MemoryBrain] ?? id;
  return <section className="brain-map" aria-label="Карта мозгов">
    <h4>Карта мозгов</h4>
    <p>Мозги растут сами в режиме простоя: ветки по словам и по смыслу, новые темы, проверка качества.</p>
    {map.proposals.map(proposal => <div className="brain-map__proposal" key={proposal.id}>
      <span>Тема «{proposal.title}» выросла в нескольких мозгах
        ({proposal.brains.map(b => names[b] ?? b).join(', ')}, фактов: {proposal.support}).
        Сделать её отдельным мозгом? Факты останутся и на старых местах.</span>
      <button type="button" disabled={busy} onClick={() => void act(() => decideBrainProposal(proposal.id, true))}>Да</button>
      <button type="button" disabled={busy} onClick={() => void act(() => decideBrainProposal(proposal.id, false))}>Не надо</button>
    </div>)}
    {error && <p role="alert">{error}</p>}
    <div className="brain-map__grid">
      {map.roots.map(root => <div className="brain-map__brain" key={root.id}>
        <strong>{title(root.id, root.title)}</strong>
        <small>{root.facts} фактов{root.growth > 0 ? ` · +${root.growth} за неделю` : ''}
          {' · '}{root.branches} веток{root.newBranches > 0 ? ` (новых: ${root.newBranches})` : ''}</small>
        {root.strong.length > 0 && <small className="brain-map__strong">
          Сильные: {root.strong.map(b => b.title).join(', ')}</small>}
        {root.sleeping.length > 0 && <small className="brain-map__sleeping">
          Засыпают: {root.sleeping.map(b => b.title).join(', ')}</small>}
        {root.custom && <button type="button" disabled={busy}
          onClick={() => void act(() => removeCustomBrain(root.id))}>Убрать мозг</button>}
      </div>)}
    </div>
  </section>;
}
