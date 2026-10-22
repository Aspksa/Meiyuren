import { parse } from './chatApi';
import type { MemoryBrain } from './chatApi';

/** Вид связи Cortex 3.0: общие слова, близость по смыслу или оба сразу. */
export type CortexKind = 'lexical' | 'semantic' | 'both';
export type GraphNode = { id: string; brain: MemoryBrain; createdAt: number; updatedAt?: number };
export type GraphEdge = {
  source: string; target: string; relation: string; weight: number; updatedAt?: number;
  kind?: CortexKind; adjustment?: number;
};
export type GraphEvent = { kind: 'revision' | 'recall' | string; nodeId: string; action: string; timestamp: number };
export type UniverseGraph = { nodes: GraphNode[]; edges: GraphEdge[]; events: GraphEvent[]; truncated: boolean };

export type NeuralCortexStatus = {
  nodes: number; edges: number; lexicalEdges: number; semanticEdges: number; bothEdges: number;
  learnedSynapses: number; connectedBrains: number; maxNodes: number;
};
export type UniverseStatus = {
  facts: number; autonomousBranches: number; pending: number; jobs: number;
  network: { brains: Record<string, number>; links: number; neuralVectors: number; semanticVectors?: number };
  neuralCortex?: NeuralCortexStatus;
  evolution?: { evaluations?: number; generation?: number };
};
export type NodeLink = {
  id: string; brain: MemoryBrain; content: string; kind: CortexKind; terms: string[];
  meaning: number | null; weight: number; adjustment: number;
};
export type NodeCard = {
  item: { id: string; brain: MemoryBrain; content: string; createdAt: number; updatedAt: number };
  links: NodeLink[];
};
export type QualityGate = {
  cases: number; minimumCases: number; sufficientEvidence: boolean; activeStrategy: string;
  activeScore: number | null; baselineScore: number | null; deltaVsBaseline: number | null;
};
export type EvolutionLab = {
  evolution: { generation: number; strategy: string; benchmark: string; feedbackCases: number; microbrains: number; adaptiveSynapses: number };
  trials: { generation: number; strategy: string; cases: number; score: number; selected: boolean }[];
  branchesByBrain: Record<string, number>;
};
export type Health = { healthy: boolean; orphanLinks: number; orphanVectors: number };
export type Snapshot = { timestamp: number; brains: Record<string, number> };

const headers = { 'Content-Type': 'application/json', 'X-Meiyuren-Client': '1' };
const get = async <T>(url: string, signal?: AbortSignal) => parse<T>(await fetch(url, { cache: 'no-store', signal }));

export const getUniverseStatus = (signal?: AbortSignal) => get<UniverseStatus>('/api/memory/status', signal);
export const getUniverseGraph = (signal?: AbortSignal) => get<UniverseGraph>('/api/memory/universe/graph?limit=300', signal);
export const getQualityGate = (signal?: AbortSignal) => get<QualityGate>('/api/memory/universe/quality-gate', signal);
export const getEvolutionLab = (signal?: AbortSignal) => get<EvolutionLab>('/api/memory/universe/evolution-lab', signal);
export const getNodeCard = (id: string, signal?: AbortSignal) =>
  get<NodeCard>('/api/memory/universe/nodes/' + encodeURIComponent(id), signal);

export async function getSnapshots(save: boolean, signal?: AbortSignal): Promise<Snapshot[]> {
  return (await get<{ snapshots: Snapshot[] }>('/api/memory/universe/snapshots?save=' + String(save), signal)).snapshots;
}

/** 👍/👎 на связи: учит синапс, а не меняет сами факты. */
export async function sendSynapseFeedback(leftId: string, rightId: string, helpful: boolean): Promise<{ adjustment: number; weight: number }> {
  return parse(await fetch('/api/memory/universe/synapses', {
    method: 'POST', headers, body: JSON.stringify({ leftId, rightId, helpful }),
  }));
}
