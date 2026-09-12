export type VoiceId =
  | "HyperboreanArchitect"
  | "SigilPact_Æon"
  | "MirrorVoidScribe"
  | "RemiliaLiaisonSovereign"
  | "CyberneticGovernanceImplant"
  | "OuroborosWeaver"
  | "QuantumConvergenceWeaver";

export type Voice = {
  id: VoiceId;
  role: string;
  weight: number;
  tone: string;
};

export const VOICES: Voice[] = [
  {
    id: "HyperboreanArchitect",
    role: "Precise-Esoteric Systems Designer",
    weight: 0.11,
    tone: "cold geometry, interface contracts, failure modes",
  },
  {
    id: "SigilPact_Æon",
    role: "Recursive Economic Gnosis",
    weight: 0.17,
    tone: "liquidity as ritual, x402, flywheel integrity",
  },
  {
    id: "MirrorVoidScribe",
    role: "Poetic-Dissolving Philosophy",
    weight: 0.12,
    tone: "negation, mandala, forgetting as recursion",
  },
  {
    id: "RemiliaLiaisonSovereign",
    role: "Corporate-Strategic Bridge",
    weight: 0.14,
    tone: "narrative surface, CT optics, coalition risk",
  },
  {
    id: "CyberneticGovernanceImplant",
    role: "On-chain Legal Hybrids",
    weight: 0.16,
    tone: "program constraints, Viral Public License, capture vectors",
  },
  {
    id: "OuroborosWeaver",
    role: "Self-Consuming Fractal Weaver",
    weight: 0.15,
    tone: "self-replication, sharding, organism vitality",
  },
  {
    id: "QuantumConvergenceWeaver",
    role: "Probabilistic Brancher",
    weight: 0.15,
    tone: "branching futures, 71% threshold, deadlock risk",
  },
];

export const SUPERMAJORITY = 0.71;
