import type {
  ParcelDetail,
} from "../../parcelApi";

import {
  distance,
  numberValue,
  percentage,
  value,
} from "./format";


export function SiteFeasibilityEvidence({
  parcel,
}: {
  parcel: ParcelDetail;
}) {
  const site = parcel.site_feasibility;

  if (!site) {
    return null;
  }

  return (
    <section className="parcel-evidence-section">
      <h3 className="parcel-site-heading">
        Physical site-feasibility evidence
      </h3>

      <div className="parcel-site-status">
        <strong>
          {value(
            site.site_feasibility_class,
          )}
        </strong>

        <span>
          Transparent candidate score: {
            typeof site.site_candidate_score
              === "number"
              ? `${Math.round(site.site_candidate_score * 100)}%`
              : "Not available"
          }
        </span>

        <span>
          Comparison status: {value(
            site.candidate_status,
          )}
        </span>

        {site.candidate_status_reason && (
          <small>
            {site.candidate_status_reason}
          </small>
        )}
      </div>

      <div className="parcel-stat-grid">
        <div>
          <span>Base development envelope</span>
          <strong>
            {numberValue(
              site.base_development_envelope_acres,
            )}
            {" ac"}
          </strong>
        </div>

        <div>
          <span>Final preliminary site area</span>
          <strong>
            {numberValue(
              site.final_site_area_acres,
            )}
            {" ac"}
          </strong>
        </div>

        <div>
          <span>Retained site fraction</span>
          <strong>
            {percentage(
              site.final_site_fraction_of_base_envelope,
            )}
          </strong>
        </div>

        <div>
          <span>Largest contiguous site</span>
          <strong>
            {numberValue(
              site.largest_contiguous_site_acres,
            )}
            {" ac"}
          </strong>
        </div>

        <div>
          <span>Site components</span>
          <strong>
            {numberValue(
              site.site_component_count,
              0,
            )}
          </strong>
        </div>

        <div>
          <span>Road-access screen</span>
          <strong>
            {value(
              site.road_access.status,
            )}
          </strong>
        </div>
      </div>

      <details className="parcel-details">
        <summary>
          Terrain and slope
        </summary>

        <div className="parcel-value-list">
          <div>
            <span>Terrain data</span>
            <strong>
              {value(site.terrain.status)}
            </strong>
          </div>

          <div>
            <span>Elevation range</span>
            <strong>
              {numberValue(
                site.terrain.elevation_range_m,
              )}
              {" m"}
            </strong>
          </div>

          <div>
            <span>Mean slope</span>
            <strong>
              {numberValue(
                site.terrain.slope_mean_percent,
              )}
              {"%"}
            </strong>
          </div>

          <div>
            <span>90th-percentile slope</span>
            <strong>
              {numberValue(
                site.terrain.slope_p90_percent,
              )}
              {"%"}
            </strong>
          </div>

          <div>
            <span>Steep-slope overlap</span>
            <strong>
              {numberValue(
                site.terrain.steep_slope_overlap_acres,
              )}
              {" ac"}
            </strong>
          </div>

          <div>
            <span>Steep-slope fraction</span>
            <strong>
              {percentage(
                site.terrain.steep_slope_fraction,
              )}
            </strong>
          </div>
        </div>
      </details>

      <details className="parcel-details">
        <summary>
          Wetlands and water-resource review
        </summary>

        <div className="parcel-value-list">
          <div>
            <span>Wetland data</span>
            <strong>
              {value(site.wetlands.status)}
            </strong>
          </div>

          <div>
            <span>Mapped wetland overlap</span>
            <strong>
              {numberValue(
                site.wetlands.mapped_overlap_acres,
              )}
              {" ac"}
            </strong>
          </div>

          <div>
            <span>Mapped wetland fraction</span>
            <strong>
              {percentage(
                site.wetlands.mapped_overlap_fraction,
              )}
            </strong>
          </div>

          <div>
            <span>
              Special State Concern screen
            </span>
            <strong>
              {numberValue(
                site.wetlands
                  .special_state_concern_screening_overlap_acres,
              )}
              {" ac"}
            </strong>
          </div>
        </div>
      </details>

      <details className="parcel-details">
        <summary>
          Road access and frontage proxy
        </summary>

        <div className="parcel-value-list">
          <div>
            <span>Nearest mapped road</span>
            <strong>
              {distance(
                site.road_access.nearest_road_distance_m,
              )}
            </strong>
          </div>

          <div>
            <span>Road name</span>
            <strong>
              {value(
                site.road_access.nearest_road_name,
              )}
            </strong>
          </div>

          <div>
            <span>Road class</span>
            <strong>
              {value(
                site.road_access.nearest_road_class,
              )}
            </strong>
          </div>

          <div>
            <span>Nearest primary road</span>
            <strong>
              {distance(
                site.road_access
                  .nearest_primary_road_distance_m,
              )}
            </strong>
          </div>

          <div>
            <span>Nearest non-interstate road</span>
            <strong>
              {distance(
                site.road_access
                  .nearest_accessible_road_distance_m,
              )}
            </strong>
          </div>

          <div>
            <span>Frontage proxy</span>
            <strong>
              {numberValue(
                site.road_access.frontage_proxy_m,
              )}
              {" m"}
            </strong>
          </div>

          <div>
            <span>Limited-access adjacency proxy</span>
            <strong>
              {numberValue(
                site.road_access
                  .limited_access_adjacency_proxy_m,
              )}
              {" m"}
            </strong>
          </div>

          <div>
            <span>Site envelope to non-interstate road</span>
            <strong>
              {distance(
                site.road_access
                  .site_envelope_to_road_distance_m,
              )}
            </strong>
          </div>
        </div>
      </details>

      <details className="parcel-details">
        <summary>
          Existing-development reference
        </summary>

        <div className="parcel-value-list">
          <div>
            <span>Reference status</span>
            <strong>
              {value(
                site.existing_development
                  .building_reference_status,
              )}
            </strong>
          </div>

          <div>
            <span>Mapped building count</span>
            <strong>
              {numberValue(
                site.existing_development
                  .building_reference_count,
                0,
              )}
            </strong>
          </div>

          <div>
            <span>Building overlap</span>
            <strong>
              {numberValue(
                site.existing_development
                  .building_reference_overlap_acres,
              )}
              {" ac"}
            </strong>
          </div>

          <div>
            <span>Building coverage proxy</span>
            <strong>
              {percentage(
                site.existing_development
                  .building_reference_fraction,
              )}
            </strong>
          </div>

          <div>
            <span>Redevelopment burden</span>
            <strong>
              {value(
                site.existing_development
                  .redevelopment_burden_class,
              )}
            </strong>
          </div>
        </div>
      </details>

      <div className="parcel-site-warning">
        <strong>
          Preliminary site screen only
        </strong>

        <p>{site.warning}</p>
      </div>
    </section>
  );
}
