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


function humanize(
  value: string | null | undefined,
): string {
  return value
    ?.replaceAll("_", " ")
    ?? "UNKNOWN";
}


function physicalSection(
  parcel: ParcelDetail,
): {
  value: string;
  detail: string;
  level: SummaryLevel;
  largest: number | null;
} {
  const site = parcel.site_feasibility;

  if (site) {
    const className =
      site.site_feasibility_class;

    const largest =
      typeof site.largest_contiguous_site_acres
      === "number"
        ? site.largest_contiguous_site_acres
        : null;

    const finalArea =
      typeof site.final_site_area_acres
      === "number"
        ? site.final_site_area_acres
        : null;

    const detail = [
      finalArea !== null
        ? `${finalArea.toFixed(1)} final preliminary site acres`
        : null,
      largest !== null
        ? `${largest.toFixed(1)}-acre largest contiguous site`
        : null,
      site.road_access.status
        ? humanize(site.road_access.status)
        : null,
    ]
      .filter(
        (value): value is string =>
          value !== null,
      )
      .join("; ");

    if (
      className
      === "STRONG_PRELIMINARY_SITE_FEASIBILITY"
    ) {
      return {
        value: "STRONG",
        detail,
        level: "positive",
        largest,
      };
    }

    if (
      className
      === "PROMISING_PRELIMINARY_SITE_FEASIBILITY"
    ) {
      return {
        value: "PROMISING",
        detail,
        level: "positive",
        largest,
      };
    }

    if (
      className
      === "LIMITED_PHYSICAL_SITE_FEASIBILITY"
    ) {
      return {
        value: "LIMITED",
        detail,
        level: "blocked",
        largest,
      };
    }

    return {
      value: "REVIEW REQUIRED",
      detail:
        detail
        || "Physical site evidence requires review",
      level: "caution",
      largest,
    };
  }

  const envelope =
    parcel.development_envelope;

  const largest =
    typeof envelope
      ?.largest_contiguous_unconstrained_acres
    === "number"
      ? envelope
        .largest_contiguous_unconstrained_acres
      : null;

  const unconstrained =
    typeof envelope
      ?.preliminary_unconstrained_area_acres
    === "number"
      ? envelope
        .preliminary_unconstrained_area_acres
      : null;

  if (
    largest === null
    || unconstrained === null
  ) {
    return {
      value: "NOT BUILT",
      detail:
        "Physical site evidence unavailable",
      level: "unknown",
      largest,
    };
  }

  if (
    largest >= 40
    && unconstrained >= 50
  ) {
    return {
      value: "PROMISING",
      detail:
        `${unconstrained.toFixed(1)} preliminary unconstrained acres; `
        + `${largest.toFixed(1)}-acre largest contiguous area`,
      level: "positive",
      largest,
    };
  }

  if (
    largest >= 15
    && unconstrained >= 20
  ) {
    return {
      value: "CONSTRAINED",
      detail:
        `${unconstrained.toFixed(1)} preliminary unconstrained acres; `
        + `${largest.toFixed(1)}-acre largest contiguous area`,
      level: "caution",
      largest,
    };
  }

  return {
    value: "LIMITED",
    detail:
      `${unconstrained.toFixed(1)} preliminary unconstrained acres; `
      + `${largest.toFixed(1)}-acre largest contiguous area`,
    level: "blocked",
    largest,
  };
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

  const physical = physicalSection(
    parcel,
  );

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
    typeof physical.largest === "number"
    && physical.largest >= 40
  ) {
    strengths.push(
      "Meaningful contiguous preliminary site area",
    );
  }

  const site = parcel.site_feasibility;

  if (
    site?.road_access.status
    === "DIRECT_MAPPED_ROAD_FRONTAGE_PROXY"
  ) {
    strengths.push(
      "Mapped road-frontage proxy is present",
    );
  }

  if (
    typeof site?.wetlands
      .mapped_overlap_fraction
    === "number"
    && site.wetlands
      .mapped_overlap_fraction <= 0.05
  ) {
    strengths.push(
      "Low mapped wetland overlap in the preliminary site envelope",
    );
  }

  if (
    typeof site?.terrain
      .steep_slope_fraction
    === "number"
    && site.terrain
      .steep_slope_fraction <= 0.10
  ) {
    strengths.push(
      "Limited mapped steep-slope overlap",
    );
  }

  if (gridLevel === "positive") {
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
      "Ownership, parcel control, and availability are unconfirmed",
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

  if (site) {
    if (
      site.wetlands
        .field_delineation_confirmed
      === false
    ) {
      unresolved.push(
        "Mapped wetlands require field delineation and permitting review",
      );
    }

    if (
      site.road_access
        .legal_access_confirmed
      === false
    ) {
      unresolved.push(
        "Legal road access and driveway approval are unconfirmed",
      );
    }

    if (
      site.terrain
        .engineering_complete
      === false
    ) {
      unresolved.push(
        "Grading, geotechnical, drainage, and detailed terrain engineering remain outstanding",
      );
    }

    if (
      site.existing_development
        .building_geometry_survey_grade
      === false
    ) {
      unresolved.push(
        "Building-footprint evidence is reference-only and requires site verification",
      );
    }
  }
  else {
    unresolved.push(
      "Terrain, wetlands, road access, and redevelopment evidence are unavailable",
    );
  }

  const blocked =
    parcel.statewide_context
      .hard_excluded
    || parcel.classification
      .availability_status
      === "PUBLIC_OR_INSTITUTIONAL"
    || physical.level === "blocked"
    || (
      typeof physical.largest === "number"
      && physical.largest < 5
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
        label: "Physical site feasibility",
        value: physical.value,
        detail: physical.detail,
        level: physical.level,
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
      ? "Resolve blocking parcel or physical-site constraints before further diligence"
      : site
        ? "Compare top parcel and assemblage candidates, then continue preliminary diligence"
        : "Continue preliminary diligence",
    nextActionLevel: blocked
      ? "blocked"
      : "positive",
  };
}
