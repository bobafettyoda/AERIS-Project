import type {
  CandidatePoint,
  EquityScreenResult,
  SiteEvaluation,
} from "./api";


export type SavedCandidate = {
  id: string;
  label: string;
  name: string;
  point: CandidatePoint;
  evaluation: SiteEvaluation;
  equity: EquityScreenResult | null;
  savedAt: string;
};


const STORAGE_KEY =
  "aeris-maryland-candidates-v1";


export function loadSavedCandidates():
SavedCandidate[] {
  try {
    const raw = window.localStorage.getItem(
      STORAGE_KEY
    );

    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);

    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed.slice(0, 5);
  } catch {
    return [];
  }
}


export function storeSavedCandidates(
  candidates: SavedCandidate[],
): void {
  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(
      candidates.slice(0, 5)
    ),
  );
}


export function nextCandidateLabel(
  candidates: SavedCandidate[],
): string {
  const labels = [
    "A",
    "B",
    "C",
    "D",
    "E",
  ];

  const used = new Set(
    candidates.map(
      (candidate) => candidate.label
    )
  );

  return (
    labels.find(
      (label) => !used.has(label)
    ) ?? "E"
  );
}
