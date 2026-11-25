import { useLanguage } from "./Language.jsx";
import { errorMessage } from "./errors.mjs";
import React, { useState } from "react";
import { Card } from "@astryxdesign/core/Card";
import { Action, Range, Empty } from "./ui.jsx";
import { Icon } from "./Icons.jsx";
import { bridge } from "./client.mjs";
import { sceneActive } from "./model.mjs";
const colors = [
  ["#f6b76c", "#ac5779"],
  ["#4c83ff", "#7966ed"],
  ["#a77bff", "#ff6aa5"],
  ["#f1dbb1", "#9a798c"],
  ["#ff5e77", "#a8558e"],
  ["#31a3a6", "#707ac4"],
];
export function SceneCards({ state, slots, full = false }) {
  const { t } = useLanguage();
  const [pending, setPending] = useState(null),
    goBlock = bridge.blockReason("scene_go"),
    offBlock = bridge.blockReason("scene_off");
  async function run(a, scene) {
    setPending(scene.id);
    try {
      await bridge.action({ a, id: scene.id, scene_identity: scene.identity, config_revision: state.config.revision });
    } catch (e) {
      bridge.report(e);
    } finally {
      setPending(null);
    }
  }
  const scenes = state.config?.scenes || [];
  if (!scenes.length)
    return (
      <Empty title={t("scenes.empty")}>
        {t("scenes.emptyHint")}
      </Empty>
    );
  return (
    <div className={`scene-grid ${full ? "full" : ""}`}>
      {scenes.map((scene, i) => {
        const active = sceneActive(state, scene.id),
          palette = colors[i % colors.length],
          slot = slots.indexOf(scene.id) + 1;
        return (
          <Card
            key={scene.id}
            className={`scene-card ${active === true ? "active" : ""}`}
            style={{ "--scene-a": palette[0], "--scene-b": palette[1] }}
          >
            <button
              className="scene-launch"
              disabled={!!goBlock || pending !== null}
              aria-label={t("scenes.play", { name: scene.label || t("scenes.unnamed", { index: i + 1 }) })}
              onClick={() => run("scene_go", scene)}
              title={errorMessage(goBlock, t) ?? t("scenes.executorHint", { executor: scene.exec })}
            >
              <div className="scene-art">
                <svg viewBox="0 0 180 92" aria-hidden="true">
                  <defs>
                    <linearGradient id={`scene-${i}`} x2=".3" y2="1">
                      <stop stopColor={palette[0]} stopOpacity=".48" />
                      <stop offset="1" stopColor={palette[1]} stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <path
                    d="M20 16H160L176 80H4Z"
                    fill="#141722"
                    stroke="#a1a0b6"
                    strokeOpacity=".16"
                  />
                  <path
                    d={`M29 10 95 81H7Z M82 10 139 81H41Z M145 10 175 81H89Z`}
                    fill={`url(#scene-${i})`}
                  />
                  <ellipse
                    cx="85"
                    cy="75"
                    rx="59"
                    ry="8"
                    fill={palette[0]}
                    opacity=".13"
                  />
                  {[29, 82, 145].map((x) => (
                    <rect
                      key={x}
                      x={x - 4}
                      y="7"
                      width="8"
                      height="4"
                      rx="1"
                      fill={palette[0]}
                    />
                  ))}
                </svg>
                {slot > 0 && <kbd>{slot}</kbd>}
                <span className="scene-play">
                  <Icon name="scenes" size={15} />
                </span>
              </div>
              <div className="scene-info">
                <b>{scene.label || t("scenes.unnamed", { index: i + 1 })}</b>
                <span>
                  <i className={active === true ? "active-dot" : ""} />
                  {pending === scene.id
                    ? t("scenes.pending")
                    : active === true
                      ? t("scenes.active")
                      : active === false
                        ? t("scenes.inactive")
                        : t("scenes.unknown")}
                </span>
              </div>
            </button>
            {full && (
              <div className="scene-detail">
                <span>Executor {scene.exec}</span>
                <button
                  disabled={!!offBlock || pending !== null}
                  title={errorMessage(offBlock, t)}
                  onClick={() => run("scene_off", scene)}
                >
                  {t("scenes.stop")}
                </button>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
export default function Scenes({ state, slots, onManage, onShortcuts }) {
  const { t } = useLanguage();
  return (
    <>
      <div className="section-heading">
        <div>
          <h2>
            {t("scenes.library")} <span>{state.config?.scenes?.length || 0}</span>
          </h2>
          <p>{t("scenes.readback")}</p>
        </div>
        <div className="button-row">
          <Action onClick={onShortcuts}>
            <Icon name="keyboard" />
            {t("scenes.assignKeys")}
          </Action>
          <Action onClick={onManage}>
            <Icon name="plus" />
            {t("scenes.recordManage")}
          </Action>
        </div>
      </div>
      <div className="scene-fade">
        <Range
          label={t("scenes.fade")}
          value={state.config?.scene_fade ?? null}
          max={30}
          step={0.5}
          suffix={` ${t("common.secondsUnit")}`}
          disabled={!bridge.ready("scene_fade")}
          onCommit={(fade) =>
            bridge
              .action({ a: "scene_fade", fade })
              .catch((e) => bridge.report(e))
          }
        />
        <p>
          {t("scenes.fadeHint")}
        </p>
      </div>
      <SceneCards state={state} slots={slots} full />
    </>
  );
}
