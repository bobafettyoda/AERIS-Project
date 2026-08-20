import {
  useCallback,
  useRef,
  useState,
} from "react";

import {
  fetchParcelBuildJob,
  fetchParcelScopeBundle,
  startZoneParcelBuild,
  type ArtifactStatus,
  type ParcelBuildJob,
  type ParcelEnvelopeCollection,
  type ParcelFeatureCollection,
  type ParcelGridEvidenceCollection,
  type ParcelPlanningEvidenceCollection,
} from "../parcelApi";


const TERMINAL_STATES = new Set([
  "completed",
  "partial_failure",
  "failed",
]);


function delay(
  milliseconds: number,
): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });
}


async function waitForJob(
  initialJob: ParcelBuildJob,
  onUpdate: (
    job: ParcelBuildJob,
  ) => void,
): Promise<ParcelBuildJob> {
  let job = initialJob;
  const deadline = Date.now() + 30 * 60 * 1000;

  while (!TERMINAL_STATES.has(job.state)) {
    if (Date.now() > deadline) {
      throw new Error(
        "Parcel build did not finish within 30 minutes.",
      );
    }

    await delay(700);
    job = await fetchParcelBuildJob(
      job.job_id,
    );
    onUpdate(job);
  }

  return job;
}


export type ParcelScopeState = {
  parcels: ParcelFeatureCollection | null;
  envelopes: ParcelEnvelopeCollection | null;
  constraints: ParcelEnvelopeCollection | null;
  gridEvidence: ParcelGridEvidenceCollection | null;
  planningEvidence: ParcelPlanningEvidenceCollection | null;
  artifacts: Record<string, ArtifactStatus>;
  job: ParcelBuildJob | null;
  loading: boolean;
  error: string | null;
};


const EMPTY_STATE: ParcelScopeState = {
  parcels: null,
  envelopes: null,
  constraints: null,
  gridEvidence: null,
  planningEvidence: null,
  artifacts: {},
  job: null,
  loading: false,
  error: null,
};


export function useParcelScope() {
  const [state, setState] =
    useState<ParcelScopeState>(
      EMPTY_STATE,
    );

  const requestGeneration = useRef(0);

  const loadZone = useCallback(
    async (
      zoneId: string,
      refresh = false,
    ): Promise<void> => {
      const requestId = ++requestGeneration.current;
      const isCurrent = () => requestGeneration.current === requestId;

      setState({
        ...EMPTY_STATE,
        loading: true,
      });

      try {
        const initialJob =
          await startZoneParcelBuild(
            zoneId,
            refresh,
          );

        if (!isCurrent()) {
          return;
        }

        setState((current) => ({
          ...current,
          job: initialJob,
          artifacts: initialJob.artifacts,
        }));

        const finishedJob =
          await waitForJob(
            initialJob,
            (job) => {
              if (!isCurrent()) {
                return;
              }
              setState((current) => ({
                ...current,
                job,
                artifacts: job.artifacts,
              }));
            },
          );

        if (!isCurrent()) {
          return;
        }

        if (
          finishedJob.state
          === "failed"
        ) {
          throw new Error(
            finishedJob.error
            ?? "Parcel build failed.",
          );
        }

        const bundle =
          await fetchParcelScopeBundle(
            finishedJob.scope_id,
          );

        if (!isCurrent()) {
          return;
        }

        const failedDomains =
          Object.entries(
            bundle.artifacts,
          )
            .filter(
              ([, artifact]) =>
                artifact.state
                === "failed",
            )
            .map(
              ([name, artifact]) =>
                `${name}: ${artifact.error ?? "unavailable"}`,
            );

        setState({
          parcels: bundle.parcels,
          envelopes:
            bundle.envelopes,
          constraints:
            bundle.constraints,
          gridEvidence:
            bundle.grid,
          planningEvidence:
            bundle.planning,
          artifacts:
            bundle.artifacts,
          job: finishedJob,
          loading: false,
          error:
            failedDomains.length > 0
              ? (
                "Some evidence domains are unavailable: "
                + failedDomains.join("; ")
              )
              : null,
        });
      }
      catch (caughtError: unknown) {
        if (!isCurrent()) {
          return;
        }
        setState((current) => ({
          ...current,
          loading: false,
          error:
            caughtError instanceof Error
              ? caughtError.message
              : (
                "Parcel scope could not be loaded."
              ),
        }));
      }
    },
    [],
  );

  const clearError = useCallback(() => {
    setState((current) => ({
      ...current,
      error: null,
    }));
  }, []);

  return {
    ...state,
    loadZone,
    clearError,
  };
}
