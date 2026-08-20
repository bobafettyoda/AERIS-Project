import type {
  ParcelDetail,
} from "../parcelApi";


type SummaryLevel =
  | "positive"
  | "caution"
  | "blocked"
  | "unknown";


type SummarySection = {
  label: string;
  value: string;
  detail: string;
  level: SummaryLevel;
};


export type ParcelScreeningSynthesis = {
  sections: SummarySection[];
  strengths: string[];
  unresolved: string[];
  nextAction: string;
  nextActionLevel: SummaryLevel;
};


function scoreLabel(
  value: number | null | undefined,
): string {
  if (typeof value !== "number") {
    return "UNKNOWN";
  }
  if (value >= 0.8) {
    return "HIGH";
  }
  if (value >= 0.7) {
    return "MODERATE";
  }
  return "LOW";
}


function scoreDetail(
  value: number | null | undefined,
): string {
  return typeof value === "number"
    ? `${Math.round(value * 100)}% technical suitability`
    : "Regional score unavailable";
}


export function summarizeParcel(
  parcel: ParcelDetail,
): ParcelScreeningSynthesis {
  const technical =
    parcel.statewide_context
      .technical_score;

  const regionalLabel =
    parcel.statewide_context
      .hard_excluded
      ? "HARD EXCLUDED"
      : scoreLabel(technical);

  const regionalLevel:
  SummaryLevel =
    parcel.statewide_context
      .hard_excluded
      ? "blocked"
      : technical === undefined
        || technical === null
        ? "unknown"
        : technical >= 0.8
          ? "positive"
          : technical >= 0.7
            ? "caution"
            : "blocked";

  const envelope =
    parcel.development_envelope;

  const largest =
    envelope
      ?.largest_contiguous_unconstrained_acres;

  const unconstrained =
    envelope
      ?.preliminary_unconstrained_area_acres;

  let physicalValue = "NOT BUILT";
  let physicalDetail =
    "Mapped development envelope unavailable";
  let physicalLevel:
  SummaryLevel = "unknown";

  if (
    typeof largest === "number"
    && typeof unconstrained === "number"
  ) {
    if (
      largest >= 40
      && unconstrained >= 50
    ) {
      physicalValue = "PROMISING";
      physicalLevel = "positive";
    }
    else if (
      largest >= 15
      && unconstrained >= 20
    ) {
      physicalValue = "CONSTRAINED";
      physicalLevel = "caution";
    }
    else {
      physicalValue = "LIMITED";
      physicalLevel = "blocked";
    }

    physicalDetail =
      `${unconstrained.toFixed(1)} preliminary unconstrained acres; `
      + `${largest.toFixed(1)}-acre largest contiguous area`;
  }

  const gridClass =
    parcel.grid_feasibility
      ?.public_grid_context_class;

  const gridValue =
    gridClass
      ?.replaceAll("_", " ")
      .replace(
        " MAPPED GRID CONTEXT",
        "",
      )
    ?? "NOT BUILT";

  const gridLevel:
  SummaryLevel =
    gridClass?.startsWith(
      "VERY_STRONG",
    )
    || gridClass?.startsWith(
      "STRONG",
    )
      ? "positive"
      : gridClass?.startsWith(
          "MODERATE",
        )
        ? "caution"
        : gridClass
          ? "blocked"
          : "unknown";

  const planningStatus =
    parcel.planning_context
      ?.decision
      .planning_review_status;

  const planningValue =
    planningStatus
      ? "REVIEW REQUIRED"
      : "NOT BUILT";

  const planningLevel:
  SummaryLevel =
    planningStatus
      ? "caution"
      : "unknown";

  const strengths: string[] = [];
  const unresolved: string[] = [];

  if (
    typeof technical === "number"
    && technical >= 0.8
  ) {
    strengths.push(
      "Strong regional technical suitability",
    );
  }

  if (
    typeof largest === "number"
    && largest >= 40
  ) {
    strengths.push(
      "Meaningful contiguous mapped land area",
    );
  }

  if (
    gridLevel === "positive"
  ) {
    strengths.push(
      "Strong public mapped-grid context",
    );
  }

  if (
    parcel.classification
      .availability_confirmed
    === false
  ) {
    unresolved.push(
      "Ownership and availability are unconfirmed",
    );
  }

  if (
    parcel.grid_feasibility
      ?.capacity
      .electrical_service_feasibility_confirmed
    === false
  ) {
    unresolved.push(
      "Utility capacity and interconnection remain unconfirmed",
    );
  }

  if (
    parcel.planning_context
      ?.decision
      .manual_local_verification_required
  ) {
    unresolved.push(
      "Authoritative local zoning, plans, and permits require verification",
    );
  }

  unresolved.push(
    "Wetlands, terrain, road access, title, and engineering remain outside the current model",
  );

  const blocked =
    parcel.statewide_context
      .hard_excluded
    || parcel.classification
      .availability_status
      === "PUBLIC_OR_INSTITUTIONAL"
    || (
      typeof largest === "number"
      && largest < 5
    );

  return {
    sections: [
      {
        label: "Regional suitability",
        value: regionalLabel,
        detail: scoreDetail(technical),
        level: regionalLevel,
      },
      {
        label: "Physical feasibility",
        value: physicalValue,
        detail: physicalDetail,
        level: physicalLevel,
      },
      {
        label: "Public grid context",
        value: gridValue,
        detail:
          parcel.grid_feasibility
            ? "Capacity remains unconfirmed"
            : "Grid evidence unavailable",
        level: gridLevel,
      },
      {
        label: "Planning and entitlement",
        value: planningValue,
        detail:
          planningStatus
            ?.replaceAll("_", " ")
          ?? "Planning evidence unavailable",
        level: planningLevel,
      },
    ],
    strengths,
    unresolved,
    nextAction: blocked
      ? "Resolve blocking parcel or land constraints before further diligence"
      : "Continue preliminary diligence",
    nextActionLevel: blocked
      ? "blocked"
      : "positive",
  };
}
