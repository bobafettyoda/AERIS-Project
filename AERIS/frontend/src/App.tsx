import {
  useState,
} from "react";

import SiteScreeningApp
  from "./SiteScreeningApp";

import StatewideApp
  from "./StatewideApp";

import "./ModeShell.css";


type ApplicationMode =
  | "point"
  | "statewide";


const STORAGE_KEY =
  "aeris-application-mode";


function initialMode():
ApplicationMode {
  const stored =
    window.localStorage.getItem(
      STORAGE_KEY,
    );

  return stored === "statewide"
    ? "statewide"
    : "point";
}


export default function App() {
  const [
    mode,
    setMode,
  ] = useState<ApplicationMode>(
    initialMode,
  );

  function selectMode(
    nextMode: ApplicationMode,
  ): void {
    setMode(nextMode);

    window.localStorage.setItem(
      STORAGE_KEY,
      nextMode,
    );
  }

  return (
    <div className="aeris-product-shell">
      <nav className="aeris-mode-bar">
        <div>
          <strong>AERIS</strong>

          <span>
            Assessment of Environmental
            Risk and Incident Siting
          </span>
        </div>

        <div className="aeris-mode-buttons">
          <button
            type="button"
            className={
              mode === "point"
                ? "active"
                : undefined
            }
            onClick={() => {
              selectMode("point");
            }}
          >
            Site evaluator
          </button>

          <button
            type="button"
            className={
              mode === "statewide"
                ? "active"
                : undefined
            }
            onClick={() => {
              selectMode(
                "statewide"
              );
            }}
          >
            Statewide explorer
          </button>
        </div>
      </nav>

      {mode === "point"
        ? <SiteScreeningApp />
        : <StatewideApp />}
    </div>
  );
}
